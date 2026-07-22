"""Record finalized, contiguous HyperIndex snapshot runs in the live DuckDB artifact."""

from __future__ import annotations

import csv
import json
import re
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from .artifact_paths import ANALYTICS_DIR, LIVE_DB_PATH
    from .enrich_token_metadata import JsonRpcClient
except ImportError:
    from artifact_paths import ANALYTICS_DIR, LIVE_DB_PATH
    from enrich_token_metadata import JsonRpcClient


CHAIN_ID = 1
FINALITY_POLICY = "ethereum_finalized"
SCOPE_VERSION = "wallet-transfer-signature-v1"
DEFAULT_HYPERINDEX_GRAPHQL_URL = "http://127.0.0.1:8080/v1/graphql"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")
HASH_PATTERN = re.compile(r"^0x[0-9a-f]{64}$")
WALLETS_PATH = ANALYTICS_DIR / "seeds" / "wallets.csv"


class SnapshotAlreadyCurrent(RuntimeError):
    """Raised when no new finalized block range exists for the configured wallet."""


@dataclass(frozen=True)
class ConfiguredWallet:
    address: str
    label: str


@dataclass(frozen=True)
class FinalizedBlock:
    number: int
    block_hash: str


@dataclass(frozen=True)
class HyperIndexMetadata:
    start_block: int
    progress_block: int
    end_block: int | None
    is_ready: bool


@dataclass(frozen=True)
class SnapshotRun:
    run_id: str
    chain_id: int
    wallet_address: str
    wallet_label: str
    from_block: int
    to_block: int
    to_block_hash: str
    scope_version: str


def read_configured_wallet(path: Path = WALLETS_PATH) -> ConfiguredWallet:
    with path.open(newline="") as source:
        wallets = list(csv.DictReader(source))
    if len(wallets) != 1:
        raise RuntimeError("Finalized snapshot builds currently require exactly one configured wallet")
    address = wallets[0]["address"].strip().lower()
    if not ADDRESS_PATTERN.fullmatch(address):
        raise RuntimeError("Configured wallet must be a canonical Ethereum address")
    return ConfiguredWallet(address=address, label=wallets[0]["ens"].strip() or address)


def _http_json(url: str, payload: dict[str, Any]) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "evm-wallet-search/0.1"},
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        return json.load(response)


def fetch_hyperindex_metadata(
    graphql_url: str,
    *,
    transport: Callable[[str, dict[str, Any]], Any] = _http_json,
) -> HyperIndexMetadata:
    payload = transport(
        graphql_url,
        {
            "query": (
                "query SnapshotMetadata($chainId: Int!) { "
                "_meta(where: {chainId: {_eq: $chainId}}) { "
                "chainId progressBlock startBlock endBlock isReady } }"
            ),
            "variables": {"chainId": CHAIN_ID},
        },
    )
    if not isinstance(payload, dict) or payload.get("errors"):
        raise RuntimeError("HyperIndex metadata query failed")
    items = payload.get("data", {}).get("_meta")
    if not isinstance(items, list) or len(items) != 1:
        raise RuntimeError("HyperIndex metadata must contain exactly one Ethereum chain row")
    row = items[0]
    if row.get("chainId") != CHAIN_ID:
        raise RuntimeError("HyperIndex metadata returned the wrong chain")
    return HyperIndexMetadata(
        start_block=int(row["startBlock"]),
        progress_block=int(row["progressBlock"]),
        end_block=None if row.get("endBlock") is None else int(row["endBlock"]),
        is_ready=bool(row["isReady"]),
    )


def resolve_finalized_block(client: JsonRpcClient) -> FinalizedBlock:
    block = client.call("eth_getBlockByNumber", ["finalized", False])
    if not isinstance(block, dict) or not block.get("number") or not block.get("hash"):
        raise RuntimeError("Ethereum RPC did not return a finalized block")
    number = int(block["number"], 16)
    block_hash = str(block["hash"]).lower()
    if not HASH_PATTERN.fullmatch(block_hash):
        raise RuntimeError("Ethereum RPC returned an invalid finalized block hash")
    return FinalizedBlock(number=number, block_hash=block_hash)


def ensure_run_table(connection: Any) -> None:
    connection.execute("create schema if not exists ops")
    connection.execute(
        """
        create table if not exists ops.pipeline_runs (
          run_id varchar primary key,
          chain_id integer not null check (chain_id = 1),
          wallet_address varchar not null,
          wallet_label varchar not null,
          from_block bigint not null,
          to_block bigint not null,
          to_block_hash varchar not null,
          events_found bigint,
          status varchar not null check (status in ('running', 'completed', 'failed')),
          completed_at timestamptz,
          scope_version varchar not null,
          check (from_block <= to_block)
        )
        """
    )


def next_run_start(
    connection: Any,
    *,
    chain_id: int,
    wallet_address: str,
    scope_version: str,
    configured_start_block: int,
) -> int:
    completed = connection.execute(
        """
        select from_block, to_block
        from ops.pipeline_runs
        where chain_id = ? and wallet_address = ? and scope_version = ? and status = 'completed'
        order by from_block, to_block
        """,
        [chain_id, wallet_address, scope_version],
    ).fetchall()
    expected_start = configured_start_block
    for from_block, to_block in completed:
        if int(from_block) != expected_start:
            raise RuntimeError(
                f"Completed snapshot runs are not contiguous at block {expected_start}"
            )
        expected_start = int(to_block) + 1
    return expected_start


def start_snapshot_run(
    *,
    database_path: Path = LIVE_DB_PATH,
    wallet: ConfiguredWallet,
    metadata: HyperIndexMetadata,
    finalized_block: FinalizedBlock,
) -> SnapshotRun:
    if metadata.end_block is not None and metadata.end_block < finalized_block.number:
        raise RuntimeError("HyperIndex endBlock is earlier than the finalized snapshot target")
    if metadata.progress_block < finalized_block.number:
        raise RuntimeError(
            "HyperIndex has not fully processed the finalized snapshot target "
            f"({metadata.progress_block} < {finalized_block.number})"
        )

    import duckdb

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database_path)) as connection:
        ensure_run_table(connection)
        active_run = connection.execute(
            """
            select run_id
            from ops.pipeline_runs
            where chain_id = ? and wallet_address = ? and scope_version = ? and status = 'running'
            limit 1
            """,
            [CHAIN_ID, wallet.address, SCOPE_VERSION],
        ).fetchone()
        if active_run is not None:
            raise RuntimeError(f"Snapshot run {active_run[0]} is already running")
        from_block = next_run_start(
            connection,
            chain_id=CHAIN_ID,
            wallet_address=wallet.address,
            scope_version=SCOPE_VERSION,
            configured_start_block=metadata.start_block,
        )
        if from_block > finalized_block.number:
            raise SnapshotAlreadyCurrent(
                f"Snapshot is already finalized through block {from_block - 1}"
            )
        run = SnapshotRun(
            run_id=str(uuid.uuid4()),
            chain_id=CHAIN_ID,
            wallet_address=wallet.address,
            wallet_label=wallet.label,
            from_block=from_block,
            to_block=finalized_block.number,
            to_block_hash=finalized_block.block_hash,
            scope_version=SCOPE_VERSION,
        )
        connection.execute(
            """
            insert into ops.pipeline_runs (
              run_id, chain_id, wallet_address, wallet_label, from_block, to_block,
              to_block_hash, events_found, status, completed_at, scope_version
            ) values (?, ?, ?, ?, ?, ?, ?, null, 'running', null, ?)
            """,
            [
                run.run_id,
                run.chain_id,
                run.wallet_address,
                run.wallet_label,
                run.from_block,
                run.to_block,
                run.to_block_hash,
                run.scope_version,
            ],
        )
    return run


def latest_completed_snapshot_run(
    *,
    database_path: Path = LIVE_DB_PATH,
    wallet: ConfiguredWallet,
    metadata: HyperIndexMetadata,
    finalized_block: FinalizedBlock,
) -> SnapshotRun:
    """Return the run backing an already-current snapshot without creating a new run."""

    import duckdb

    with duckdb.connect(str(database_path)) as connection:
        ensure_run_table(connection)
        next_block = next_run_start(
            connection,
            chain_id=CHAIN_ID,
            wallet_address=wallet.address,
            scope_version=SCOPE_VERSION,
            configured_start_block=metadata.start_block,
        )
        row = connection.execute(
            """
            select run_id, chain_id, wallet_address, wallet_label, from_block, to_block,
              to_block_hash, scope_version
            from ops.pipeline_runs
            where chain_id = ? and wallet_address = ? and scope_version = ? and status = 'completed'
            order by to_block desc
            limit 1
            """,
            [CHAIN_ID, wallet.address, SCOPE_VERSION],
        ).fetchone()
    if row is None or next_block != finalized_block.number + 1:
        raise RuntimeError("No completed snapshot matches the current finalized block")
    if str(row[6]).lower() != finalized_block.block_hash:
        raise RuntimeError("The recorded finalized block hash does not match Ethereum RPC")
    return SnapshotRun(
        run_id=str(row[0]),
        chain_id=int(row[1]),
        wallet_address=str(row[2]),
        wallet_label=str(row[3]),
        from_block=int(row[4]),
        to_block=int(row[5]),
        to_block_hash=str(row[6]),
        scope_version=str(row[7]),
    )


def finish_snapshot_run(
    run: SnapshotRun,
    *,
    database_path: Path = LIVE_DB_PATH,
    succeeded: bool,
) -> None:
    import duckdb

    with duckdb.connect(str(database_path)) as connection:
        if succeeded:
            events_found = connection.execute(
                """
                select count(*)
                from wallet_events
                where chain_id = ? and wallet_address = ? and block_number between ? and ?
                """,
                [run.chain_id, run.wallet_address, run.from_block, run.to_block],
            ).fetchone()[0]
            connection.execute(
                """
                update ops.pipeline_runs
                set events_found = ?, status = 'completed', completed_at = ?
                where run_id = ? and status = 'running'
                """,
                [events_found, datetime.now(timezone.utc), run.run_id],
            )
        else:
            connection.execute(
                """
                update ops.pipeline_runs
                set status = 'failed', completed_at = ?
                where run_id = ? and status = 'running'
                """,
                [datetime.now(timezone.utc), run.run_id],
            )


def dbt_snapshot_environment(run: SnapshotRun, *, coverage_start_block: int) -> dict[str, str]:
    return {
        "EVM_WALLET_SNAPSHOT_RUN_ID": run.run_id,
        "EVM_WALLET_SNAPSHOT_START_BLOCK": str(coverage_start_block),
        "EVM_WALLET_SNAPSHOT_INCREMENT_START_BLOCK": str(run.from_block),
        "EVM_WALLET_SNAPSHOT_END_BLOCK": str(run.to_block),
        "EVM_WALLET_SNAPSHOT_END_BLOCK_HASH": run.to_block_hash,
        "EVM_WALLET_SNAPSHOT_FINALITY_POLICY": FINALITY_POLICY,
        "EVM_WALLET_SNAPSHOT_SCOPE_VERSION": run.scope_version,
    }
