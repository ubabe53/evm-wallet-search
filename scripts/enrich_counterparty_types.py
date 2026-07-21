#!/usr/bin/env python3
"""Collect pinned-block bytecode evidence for distinct Ethereum counterparties."""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .artifact_paths import ACCOUNT_EVIDENCE_DB_PATH, LIVE_DB_PATH
    from .enrich_token_metadata import JsonRpcClient
    from .project_config import resolved_runtime
except ImportError:
    from artifact_paths import ACCOUNT_EVIDENCE_DB_PATH, LIVE_DB_PATH
    from enrich_token_metadata import JsonRpcClient
    from project_config import resolved_runtime


EVIDENCE_SCHEMA_VERSION = "account-evidence-v2"
DEFAULT_BATCH_SIZE = 100
DEFAULT_MAX_RETRIES = 2
DEFAULT_FALLBACK_CONFIRMATIONS = 64
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def ensure_dependencies() -> None:
    if importlib.util.find_spec("duckdb") is not None:
        return
    requirements = Path(__file__).resolve().parents[1] / "analytics" / "requirements.txt"
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(requirements)], check=True)


def ensure_evidence_store(path: Path = ACCOUNT_EVIDENCE_DB_PATH) -> None:
    """Create the ignored, local account-evidence store when it is absent."""

    ensure_dependencies()
    import duckdb

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    try:
        connection.execute(
            """
            create table if not exists account_evidence (
              chain_id integer not null,
              address varchar not null,
              account_type varchar not null,
              code_state varchar not null,
              code_size_bytes bigint,
              observation_block_number bigint not null,
              observation_block_hash varchar,
              observation_block_timestamp timestamptz not null,
              eip7702_delegation_target varchar,
              fetch_status varchar not null,
              reason_code varchar not null,
              finality_policy varchar not null,
              evidence_schema_version varchar not null,
              fetched_at timestamptz not null,
              primary key (chain_id, address)
            )
            """
        )
    finally:
        connection.close()


def read_successful_addresses(path: Path = ACCOUNT_EVIDENCE_DB_PATH) -> set[str]:
    ensure_evidence_store(path)
    import duckdb

    connection = duckdb.connect(str(path), read_only=True)
    try:
        return {
            row[0]
            for row in connection.execute(
                "select address from account_evidence where chain_id = 1 and fetch_status = 'complete'"
            ).fetchall()
        }
    finally:
        connection.close()


def select_candidates(
    connection: Any,
    successful_addresses: set[str],
    limit: int | None = None,
) -> list[str]:
    """Return each nonzero, nonself event counterparty at most once."""

    rows = connection.execute(
        """
        select lower(counterparty_address) as address, count(*) as transfer_count
        from wallet_events
        where chain_id = 1
          and lower(counterparty_address) != ?
          and lower(counterparty_address) != lower(wallet_address)
        group by address
        order by transfer_count desc, address
        """,
        [ZERO_ADDRESS],
    ).fetchall()
    eligible = [row[0] for row in rows if row[0] not in successful_addresses]
    return eligible if limit is None else eligible[:limit]


def decode_code(value: str | None) -> tuple[str, str, int | None, str | None, str, str]:
    """Map observed bytecode to the public binary type and internal code state."""

    if value is None:
        return "unknown", "unknown", None, None, "failed", "code_lookup_missing"
    normalized = value.removeprefix("0x")
    try:
        raw = bytes.fromhex(normalized)
    except ValueError:
        return "unknown", "unknown", None, None, "failed", "code_lookup_malformed"
    if not raw:
        return "eoa_candidate", "no_code", 0, None, "complete", "no_code_observed"
    if len(raw) == 23 and raw[:3] == bytes.fromhex("ef0100"):
        return (
            "eoa_candidate",
            "eip7702_delegated",
            23,
            "0x" + raw[3:].hex(),
            "complete",
            "eip7702_delegation_observed",
        )
    return "contract", "contract_code", len(raw), None, "complete", "contract_code_observed"


def resolve_observation_block(
    client: JsonRpcClient,
    fallback_confirmations: int = DEFAULT_FALLBACK_CONFIRMATIONS,
) -> tuple[str, dict[str, Any], str]:
    """Resolve one concrete safe block, falling back to a confirmed head."""

    try:
        block = client.call("eth_getBlockByNumber", ["safe", False])
        policy = "safe"
    except (OSError, RuntimeError, TimeoutError):
        block = None
        policy = ""
    if not isinstance(block, dict) or not block.get("number"):
        latest_tag = client.call("eth_blockNumber", [])
        latest_number = int(latest_tag, 16)
        pinned_number = max(0, latest_number - fallback_confirmations)
        block = client.call("eth_getBlockByNumber", [hex(pinned_number), False])
        policy = f"latest_minus_{fallback_confirmations}"
    if (
        not isinstance(block, dict)
        or not isinstance(block.get("number"), str)
        or not isinstance(block.get("hash"), str)
        or not isinstance(block.get("timestamp"), str)
    ):
        raise RuntimeError("Could not resolve a concrete Ethereum observation block")
    return hex(int(block["number"], 16)), block, policy


def fetch_code_batch(
    client: JsonRpcClient,
    addresses: list[str],
    block_tag: str,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> dict[str, str | None]:
    """Fetch one bounded JSON-RPC batch and retry only unresolved calls."""

    results: dict[str, str | None] = {}
    pending = addresses
    for _attempt in range(max_retries + 1):
        if not pending:
            break
        requests = [("eth_getCode", [address, block_tag], (address, "code")) for address in pending]
        try:
            batch_results = client.batch(requests)
        except (OSError, RuntimeError, TimeoutError):
            batch_results = {}
        next_pending = []
        for address in pending:
            value = batch_results.get((address, "code"))
            if isinstance(value, str):
                results[address] = value
            else:
                next_pending.append(address)
        pending = next_pending
    results.update({address: None for address in pending})
    return results


def build_evidence_rows(
    addresses: list[str],
    code_results: dict[str, str | None],
    block: dict[str, Any],
    finality_policy: str,
) -> list[dict[str, Any]]:
    fetched_at = datetime.now(timezone.utc)
    block_timestamp = datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc)
    block_number = int(block["number"], 16)
    rows = []
    for address in addresses:
        account_type, code_state, code_size, delegation_target, status, reason = decode_code(
            code_results.get(address)
        )
        rows.append(
            {
                "chain_id": 1,
                "address": address,
                "account_type": account_type,
                "code_state": code_state,
                "code_size_bytes": code_size,
                "observation_block_number": block_number,
                "observation_block_hash": block["hash"].lower(),
                "observation_block_timestamp": block_timestamp,
                "eip7702_delegation_target": delegation_target,
                "fetch_status": status,
                "reason_code": reason,
                "finality_policy": finality_policy,
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "fetched_at": fetched_at,
            }
        )
    return rows


def write_evidence_rows(
    rows: list[dict[str, Any]],
    path: Path = ACCOUNT_EVIDENCE_DB_PATH,
) -> None:
    """Checkpoint a batch without overwriting any successful prior observation."""

    if not rows:
        return
    ensure_evidence_store(path)
    import duckdb

    columns = [
        "chain_id",
        "address",
        "account_type",
        "code_state",
        "code_size_bytes",
        "observation_block_number",
        "observation_block_hash",
        "observation_block_timestamp",
        "eip7702_delegation_target",
        "fetch_status",
        "reason_code",
        "finality_policy",
        "evidence_schema_version",
        "fetched_at",
    ]
    connection = duckdb.connect(str(path))
    try:
        connection.begin()
        connection.executemany(
            "delete from account_evidence where chain_id = ? and address = ? and fetch_status != 'complete'",
            [(row["chain_id"], row["address"]) for row in rows],
        )
        connection.executemany(
            f"insert into account_evidence ({', '.join(columns)}) values ({', '.join('?' for _ in columns)}) "
            "on conflict do nothing",
            [[row[column] for column in columns] for row in rows],
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, help="Optional cap for a deliberate partial run")
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--max-retries", type=int)
    parser.add_argument("--fallback-confirmations", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = resolved_runtime()
    batch_size = args.batch_size or int(runtime.get("account_evidence_batch_size") or DEFAULT_BATCH_SIZE)
    max_retries = args.max_retries if args.max_retries is not None else int(
        runtime.get("account_evidence_max_retries") or DEFAULT_MAX_RETRIES
    )
    fallback_confirmations = args.fallback_confirmations if args.fallback_confirmations is not None else int(
        runtime.get("account_evidence_fallback_confirmations") or DEFAULT_FALLBACK_CONFIRMATIONS
    )
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be positive")
    if batch_size <= 0 or max_retries < 0 or fallback_confirmations < 0:
        raise SystemExit("Batch size must be positive; retries and fallback confirmations cannot be negative")
    if not LIVE_DB_PATH.exists():
        raise SystemExit("Live analytics database is missing; run bun run analytics:build:hyperindex first")

    ensure_dependencies()
    import duckdb

    successful = read_successful_addresses()
    analytics = duckdb.connect(str(LIVE_DB_PATH), read_only=True)
    try:
        addresses = select_candidates(analytics, successful, args.limit)
    finally:
        analytics.close()
    if not addresses:
        print("No unresolved counterparty addresses found")
        return

    rpc_url = runtime["ethereum_rpc_url"]
    if not rpc_url:
        raise SystemExit("No Ethereum RPC URL or public fallback is configured")
    client = JsonRpcClient(str(rpc_url))
    chain_id = int(client.call("eth_chainId", []), 16)
    if chain_id != 1:
        raise SystemExit(f"Account enrichment requires Ethereum mainnet, got chain ID {chain_id}")
    block_tag, block, finality_policy = resolve_observation_block(client, fallback_confirmations)

    complete = 0
    failed = 0
    for offset in range(0, len(addresses), batch_size):
        batch = addresses[offset : offset + batch_size]
        code_results = fetch_code_batch(client, batch, block_tag, max_retries)
        rows = build_evidence_rows(batch, code_results, block, finality_policy)
        write_evidence_rows(rows)
        complete += sum(row["fetch_status"] == "complete" for row in rows)
        failed += sum(row["fetch_status"] == "failed" for row in rows)
        print(f"Checkpointed {min(offset + len(batch), len(addresses))}/{len(addresses)} addresses")

    print(
        f"Collected account code evidence at block {int(block_tag, 16)} ({finality_policy}): "
        f"complete={complete}, failed={failed}"
    )


if __name__ == "__main__":
    main()
