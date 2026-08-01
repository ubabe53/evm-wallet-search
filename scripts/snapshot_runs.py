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
    from .enrich_token_metadata import JsonRpcCaller
except ImportError:
    from artifact_paths import ANALYTICS_DIR, LIVE_DB_PATH
    from enrich_token_metadata import JsonRpcCaller


CHAIN_ID = 1
FINALITY_POLICY = "ethereum_finalized"
SCOPE_VERSION = "wallet-transfer-signature-v1"
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
class ScanGeneration:
    generation_id: str
    chain_id: int
    from_block: int
    to_block: int
    to_block_hash: str
    scope_version: str


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
    generation_id: str
    original_input: str = ""
    normalized_name: str | None = None
    resolver_source: str = "legacy-configured-wallet"
    observation_block_number: int = 0
    observation_block_hash: str = ""
    observation_timestamp: datetime = datetime.min.replace(tzinfo=timezone.utc)


def read_configured_wallets(path: Path = WALLETS_PATH) -> list[ConfiguredWallet]:
    with path.open(newline="") as source:
        wallets = list(csv.DictReader(source))
    if not wallets:
        raise RuntimeError("At least one configured wallet is required")
    result = []
    seen = set()
    for row in wallets:
        address = row["address"].strip().lower()
        if not ADDRESS_PATTERN.fullmatch(address):
            raise RuntimeError("Configured wallet must be a canonical Ethereum address")
        if address in seen:
            raise RuntimeError(f"Configured wallet is duplicated: {address}")
        seen.add(address)
        result.append(ConfiguredWallet(address=address, label=row["ens"].strip() or address))
    return result


def read_configured_wallet(path: Path = WALLETS_PATH) -> ConfiguredWallet:
    """Compatibility helper for single-wallet callers and fixture tooling."""

    wallets = read_configured_wallets(path)
    if len(wallets) != 1:
        raise RuntimeError("This caller requires exactly one configured wallet")
    return wallets[0]


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


def resolve_finalized_block(client: JsonRpcCaller) -> FinalizedBlock:
    block = client.call("eth_getBlockByNumber", ["finalized", False])
    if not isinstance(block, dict) or not block.get("number") or not block.get("hash"):
        raise RuntimeError("Ethereum RPC did not return a finalized block")
    number = int(block["number"], 16)
    block_hash = str(block["hash"]).lower()
    if not HASH_PATTERN.fullmatch(block_hash):
        raise RuntimeError("Ethereum RPC returned an invalid finalized block hash")
    return FinalizedBlock(number=number, block_hash=block_hash)


def resolve_snapshot_target(
    client: JsonRpcCaller,
    metadata: HyperIndexMetadata,
) -> FinalizedBlock:
    """Pin the newest block that is both fully indexed and finalized."""

    finalized_head = resolve_finalized_block(client)
    target_number = min(metadata.progress_block, finalized_head.number)
    if metadata.end_block is not None:
        target_number = min(target_number, metadata.end_block)
    if target_number < metadata.start_block:
        raise RuntimeError("HyperIndex has not processed its configured start block")
    if target_number == finalized_head.number:
        return finalized_head

    block = client.call("eth_getBlockByNumber", [hex(target_number), False])
    if not isinstance(block, dict) or not block.get("number") or not block.get("hash"):
        raise RuntimeError("Ethereum RPC did not return the indexed snapshot target")
    number = int(block["number"], 16)
    block_hash = str(block["hash"]).lower()
    if number != target_number or not HASH_PATTERN.fullmatch(block_hash):
        raise RuntimeError("Ethereum RPC returned an invalid indexed snapshot target")
    return FinalizedBlock(number=number, block_hash=block_hash)


def ensure_run_table(connection: Any) -> None:
    connection.execute("create schema if not exists ops")
    target_exists = connection.execute(
        "select count(*) from information_schema.tables where table_schema = 'ops' and table_name = 'wallet_targets'"
    ).fetchone()[0]
    target_columns = {
        row[1] for row in connection.execute("pragma table_info('ops.wallet_targets')").fetchall()
    } if target_exists else set()
    if "target_id" in target_columns:
        connection.execute("alter table ops.wallet_targets rename to wallet_targets_legacy")
    connection.execute(
        """
        create table if not exists ops.wallet_targets (
          chain_id integer not null check (chain_id = 1),
          wallet_address varchar not null,
          wallet_label varchar not null,
          created_at timestamptz not null default current_timestamp,
          primary key (chain_id, wallet_address)
        )
        """
    )
    if "target_id" in target_columns:
        connection.execute(
            """
            insert into ops.wallet_targets (chain_id, wallet_address, wallet_label, created_at)
            select chain_id, wallet_address, wallet_label, created_at
            from ops.wallet_targets_legacy
            on conflict (chain_id, wallet_address) do update set wallet_label = excluded.wallet_label
            """
        )
        connection.execute("drop table ops.wallet_targets_legacy")
    connection.execute(
        """
        create table if not exists ops.scan_generations (
          generation_id varchar primary key,
          chain_id integer not null check (chain_id = 1),
          wallet_address varchar not null,
          from_block bigint not null,
          to_block bigint not null,
          to_block_hash varchar not null,
          scope_version varchar not null,
          status varchar not null check (status in ('running', 'completed', 'failed')),
          started_at timestamptz not null,
          completed_at timestamptz,
          check (from_block <= to_block)
        )
        """
    )
    connection.execute(
        """
        create table if not exists ops.pipeline_runs (
          run_id varchar primary key,
          chain_id integer not null check (chain_id = 1),
          generation_id varchar not null,
          wallet_address varchar not null,
          wallet_label varchar not null,
          from_block bigint not null,
          to_block bigint not null,
          to_block_hash varchar not null,
          events_found bigint,
          status varchar not null check (status in ('running', 'completed', 'failed')),
          completed_at timestamptz,
          scope_version varchar not null,
          original_input varchar,
          normalized_name varchar,
          resolver_source varchar,
          observation_block_number bigint,
          observation_block_hash varchar,
          observation_timestamp timestamptz,
          unique (generation_id, chain_id, wallet_address),
          check (from_block <= to_block)
        )
        """
    )
    columns = {row[1] for row in connection.execute("pragma table_info('ops.pipeline_runs')").fetchall()}
    if "generation_id" not in columns:
        # Preserve an already-built artifact while allowing new runs to carry generation lineage.
        connection.execute("alter table ops.pipeline_runs add column generation_id varchar")
    generation_columns = {
        row[1] for row in connection.execute("pragma table_info('ops.scan_generations')").fetchall()
    }
    if "wallet_address" not in generation_columns:
        connection.execute("alter table ops.scan_generations rename to scan_generations_legacy")
        connection.execute(
            """
            create table ops.scan_generations (
              generation_id varchar primary key,
              chain_id integer not null check (chain_id = 1),
              wallet_address varchar not null,
              from_block bigint not null,
              to_block bigint not null,
              to_block_hash varchar not null,
              scope_version varchar not null,
              status varchar not null check (status in ('running', 'completed', 'failed')),
              started_at timestamptz not null,
              completed_at timestamptz,
              check (from_block <= to_block)
            )
            """
        )
        connection.execute(
            "update ops.pipeline_runs set generation_id = 'legacy:' || run_id "
            "where generation_id is not null"
        )
        connection.execute(
            """
            insert into ops.scan_generations
            select generation_id, chain_id, wallet_address, from_block, to_block, to_block_hash,
              scope_version, status, started_at, completed_at
            from (
              select r.generation_id, r.chain_id, r.wallet_address, r.from_block, r.to_block,
                r.to_block_hash, r.scope_version, r.status,
                coalesce(r.completed_at, current_timestamp) as started_at, r.completed_at,
                row_number() over (partition by r.generation_id, r.wallet_address order by r.run_id) as rn
              from ops.pipeline_runs r
              where r.generation_id is not null
            )
            where rn = 1
            """
        )
        connection.execute("drop table ops.scan_generations_legacy")
    legacy_runs = connection.execute(
        "select run_id, chain_id, wallet_address, from_block, to_block, to_block_hash, scope_version, status, completed_at "
        "from ops.pipeline_runs where generation_id is null"
    ).fetchall()
    for run_id, chain_id, wallet_address, from_block, to_block, block_hash, scope_version, status, completed_at in legacy_runs:
        generation_id = f"legacy:{run_id}"
        connection.execute(
            "insert into ops.scan_generations values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "on conflict (generation_id) do nothing",
            [generation_id, chain_id, wallet_address, from_block, to_block, block_hash, scope_version, status,
             completed_at or datetime.now(timezone.utc), completed_at],
        )
        connection.execute(
            "update ops.pipeline_runs set generation_id = ? where run_id = ?",
            [generation_id, run_id],
        )
    for column, definition in (
        ("original_input", "varchar"),
        ("normalized_name", "varchar"),
        ("resolver_source", "varchar"),
        ("observation_block_number", "bigint"),
        ("observation_block_hash", "varchar"),
        ("observation_timestamp", "timestamptz"),
    ):
        connection.execute(
            f"alter table ops.pipeline_runs add column if not exists {column} {definition}"
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
    scan_input: Any | None = None,
) -> SnapshotRun:
    return start_snapshot_runs(
        database_path=database_path,
        wallets=[wallet],
        metadata=metadata,
        finalized_block=finalized_block,
        scan_input=scan_input,
    )[0]


def start_snapshot_runs(
    *,
    database_path: Path = LIVE_DB_PATH,
    wallets: list[ConfiguredWallet],
    metadata: HyperIndexMetadata,
    finalized_block: FinalizedBlock,
    scan_input: Any | None = None,
) -> list[SnapshotRun]:
    """Create independent finalized generations and runs for wallets that need coverage."""

    if not wallets:
        raise RuntimeError("At least one configured wallet is required")
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
        from_blocks = {}
        for wallet in wallets:
            connection.execute(
                "insert into ops.wallet_targets (chain_id, wallet_address, wallet_label) values (?, ?, ?) "
                "on conflict (chain_id, wallet_address) do update set wallet_label = excluded.wallet_label",
                [CHAIN_ID, wallet.address, wallet.label],
            )
            from_blocks[wallet.address] = next_run_start(
                connection, chain_id=CHAIN_ID, wallet_address=wallet.address,
                scope_version=SCOPE_VERSION, configured_start_block=metadata.start_block,
            )
        pending_wallets = [
            wallet for wallet in wallets if from_blocks[wallet.address] <= finalized_block.number
        ]
        if not pending_wallets:
            raise SnapshotAlreadyCurrent(
                f"Snapshot is already finalized through block {finalized_block.number}"
            )
        runs = []
        for wallet in pending_wallets:
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
            generation_id = str(uuid.uuid4())
            from_block = from_blocks[wallet.address]
            if scan_input is None:
                provenance = (
                    wallet.label,
                    wallet.label.lower() if wallet.label.lower().endswith(".eth") else None,
                    "legacy-configured-wallet",
                    finalized_block.number,
                    finalized_block.block_hash,
                    datetime.now(timezone.utc),
                )
            else:
                if scan_input.resolved_address != wallet.address:
                    raise RuntimeError("Resolved scan input does not match the configured wallet")
                provenance = (
                    scan_input.original_input,
                    scan_input.normalized_name,
                    scan_input.resolver_source,
                    scan_input.observation_block_number,
                    scan_input.observation_block_hash,
                    scan_input.observed_at,
                )
            connection.execute(
                "insert into ops.scan_generations values (?, ?, ?, ?, ?, ?, ?, 'running', ?, null)",
                [generation_id, CHAIN_ID, wallet.address, from_block, finalized_block.number,
                 finalized_block.block_hash, SCOPE_VERSION, datetime.now(timezone.utc)],
            )
            run = SnapshotRun(
                run_id=str(uuid.uuid4()), chain_id=CHAIN_ID, generation_id=generation_id,
                wallet_address=wallet.address, wallet_label=wallet.label,
                from_block=from_block, to_block=finalized_block.number,
                to_block_hash=finalized_block.block_hash, scope_version=SCOPE_VERSION,
                original_input=provenance[0], normalized_name=provenance[1],
                resolver_source=provenance[2], observation_block_number=provenance[3],
                observation_block_hash=provenance[4], observation_timestamp=provenance[5],
            )
            connection.execute(
                """
                insert into ops.pipeline_runs (
                  run_id, chain_id, generation_id, wallet_address, wallet_label, from_block, to_block,
                  to_block_hash, events_found, status, completed_at, scope_version,
                  original_input, normalized_name, resolver_source, observation_block_number,
                  observation_block_hash, observation_timestamp
                ) values (?, ?, ?, ?, ?, ?, ?, ?, null, 'running', null, ?, ?, ?, ?, ?, ?, ?)
                """,
                [run.run_id, run.chain_id, run.generation_id, run.wallet_address, run.wallet_label,
                 run.from_block, run.to_block, run.to_block_hash, run.scope_version,
                 run.original_input, run.normalized_name, run.resolver_source,
                 run.observation_block_number, run.observation_block_hash, run.observation_timestamp],
            )
            runs.append(run)
    return runs


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
            select run_id, chain_id, generation_id, wallet_address, wallet_label, from_block, to_block,
              to_block_hash, scope_version, original_input, normalized_name, resolver_source,
              observation_block_number, observation_block_hash, observation_timestamp
            from ops.pipeline_runs
            where chain_id = ? and wallet_address = ? and scope_version = ? and status = 'completed'
            order by to_block desc
            limit 1
            """,
            [CHAIN_ID, wallet.address, SCOPE_VERSION],
        ).fetchone()
    if row is None or next_block != finalized_block.number + 1:
        raise RuntimeError("No completed snapshot matches the current finalized block")
    if str(row[7]).lower() != finalized_block.block_hash:
        raise RuntimeError("The recorded finalized block hash does not match Ethereum RPC")
    return SnapshotRun(
        run_id=str(row[0]),
        chain_id=int(row[1]),
        generation_id=str(row[2]),
        wallet_address=str(row[3]),
        wallet_label=str(row[4]),
        from_block=int(row[5]),
        to_block=int(row[6]),
        to_block_hash=str(row[7]),
        scope_version=str(row[8]),
        original_input=str(row[9] or row[4]),
        normalized_name=None if row[10] is None else str(row[10]),
        resolver_source=str(row[11] or "legacy-configured-wallet"),
        observation_block_number=int(row[12] or row[6]),
        observation_block_hash=str(row[13] or row[7]),
        observation_timestamp=row[14] or datetime.now(timezone.utc),
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
            event_count_row = connection.execute(
                """
                select count(*)
                from wallet_events
                where chain_id = ? and wallet_address = ? and block_number between ? and ?
                """,
                [run.chain_id, run.wallet_address, run.from_block, run.to_block],
            ).fetchone()
            if event_count_row is None:
                raise RuntimeError("Could not count events for the completed snapshot run")
            events_found = event_count_row[0]
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
        generation_status = connection.execute(
            "select status from ops.pipeline_runs where generation_id = ?",
            [run.generation_id],
        ).fetchone()
        if generation_status:
            connection.execute(
                "update ops.scan_generations set status = ?, completed_at = ? where generation_id = ?",
                [generation_status[0], datetime.now(timezone.utc), run.generation_id],
            )


def dbt_snapshot_environment(run: SnapshotRun, *, coverage_start_block: int) -> dict[str, str]:
    return {
        "EVM_WALLET_SNAPSHOT_RUN_ID": run.run_id,
        "EVM_WALLET_SNAPSHOT_START_BLOCK": str(coverage_start_block),
        "EVM_WALLET_SNAPSHOT_END_BLOCK": str(run.to_block),
        "EVM_WALLET_SNAPSHOT_END_BLOCK_HASH": run.to_block_hash,
        "EVM_WALLET_SNAPSHOT_FINALITY_POLICY": FINALITY_POLICY,
        "EVM_WALLET_SNAPSHOT_SCOPE_VERSION": run.scope_version,
        "EVM_WALLET_SNAPSHOT_GENERATION_ID": run.generation_id,
    }
