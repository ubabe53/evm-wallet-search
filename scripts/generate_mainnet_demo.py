#!/usr/bin/env python3
"""Generate the checked-in finalized-mainnet dashboard snapshot from a live artifact."""

from __future__ import annotations

import argparse
import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .enrich_counterparty_types import (
        build_evidence_rows,
        fetch_code_batch,
        resolve_observation_block,
    )
    from .enrich_token_metadata import JsonRpcClient, fetch_metadata
    from .project_config import resolved_runtime
except ImportError:
    from enrich_counterparty_types import (
        build_evidence_rows,
        fetch_code_batch,
        resolve_observation_block,
    )
    from enrich_token_metadata import JsonRpcClient, fetch_metadata
    from project_config import resolved_runtime


ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "analytics" / "seeds"
WALLET_ADDRESS = "0x11c24f0031b4c35e2e9353764edc61299291e0af"
WALLET_LABEL = "Gitcoin Schelling Point multisig"
ATTRIBUTION_SOURCE_URL = "https://manual.gitcoin.co/introduction-and-overview/dao-finances"
SNAPSHOT_SCHEMA_VERSION = "mainnet-demo-snapshot-v1"
TRANSFER_SCOPE_VERSION = "wallet-transfer-signature-v1"
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

EVENT_COLUMNS = (
    "chain_id",
    "block_number",
    "block_hash",
    "block_timestamp",
    "transaction_hash",
    "transaction_index",
    "transaction_from_address",
    "transaction_to_address",
    "log_index",
    "token_address",
    "from_address",
    "to_address",
    "value_raw",
)
TOKEN_COLUMNS = (
    "token_address",
    "name",
    "symbol",
    "decimals",
    "rpc_block_number",
    "fetched_at",
    "fetch_status",
    "error_code",
)
ACCOUNT_COLUMNS = (
    "chain_id",
    "address",
    "account_type",
    "code_state",
    "code_size_bytes",
    "observation_block_number",
    "observation_block_hash",
    "observation_block_timestamp",
    "finality_policy",
    "eip7702_delegation_target",
    "fetch_status",
    "reason_code",
    "evidence_schema_version",
    "fetched_at",
)
SNAPSHOT_COLUMNS = (
    "chain_id",
    "wallet_address",
    "snapshot_run_id",
    "snapshot_generation_id",
    "snapshot_start_block",
    "snapshot_end_block",
    "snapshot_end_block_hash",
    "snapshot_finality_policy",
    "snapshot_scope_version",
    "snapshot_generated_at",
    "snapshot_source",
    "snapshot_schema_version",
    "wallet_attribution_source_url",
)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalized_row(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for column in columns:
        value = row.get(column)
        if isinstance(value, datetime):
            value = iso_utc(value)
        normalized[column] = "" if value is None else value
    return normalized


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
            writer.writeheader()
            writer.writerows(normalized_row(row, columns) for row in rows)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def write_json(path: Path, payload: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(payload, output, indent=2, sort_keys=True)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def query_dicts(connection: Any, query: str, parameters: list[Any]) -> list[dict[str, Any]]:
    result = connection.execute(query, parameters)
    columns = [description[0] for description in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def load_snapshot(connection: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    metadata = query_dicts(
        connection,
        """
        select
          metadata.chain_id,
          metadata.wallet_address,
          metadata.snapshot_run_id,
          metadata.snapshot_generation_id,
          metadata.snapshot_start_block,
          metadata.snapshot_end_block,
          metadata.snapshot_end_block_hash,
          metadata.snapshot_finality_policy,
          metadata.snapshot_scope_version,
          runs.completed_at as snapshot_generated_at,
          metadata.transfer_count as cumulative_event_count
        from pipeline_metadata as metadata
        join ops.pipeline_runs as runs on runs.run_id = metadata.snapshot_run_id
        where metadata.wallet_address = ? and runs.status = 'completed'
        """,
        [WALLET_ADDRESS],
    )
    if len(metadata) != 1:
        raise RuntimeError(f"Expected one completed snapshot for {WALLET_ADDRESS}, found {len(metadata)}")
    snapshot = metadata[0]
    if snapshot["chain_id"] != 1:
        raise RuntimeError("The public demo snapshot must be Ethereum mainnet")
    if snapshot["snapshot_start_block"] != 0:
        raise RuntimeError("The public demo snapshot must cover the configured wallet from block 0")
    if snapshot["snapshot_finality_policy"] != "ethereum_finalized":
        raise RuntimeError("The public demo snapshot must end at an Ethereum finalized block")
    if snapshot["snapshot_scope_version"] != TRANSFER_SCOPE_VERSION:
        raise RuntimeError("The public demo snapshot has an unexpected semantic scope")

    events = query_dicts(
        connection,
        """
        select
          chain_id,
          block_number,
          block_hash,
          cast(epoch(block_timestamp) as bigint) as block_timestamp,
          transaction_hash,
          transaction_index,
          transaction_from_address,
          transaction_to_address,
          log_index,
          token_address,
          from_address,
          to_address,
          value_raw
        from int_wallet_transfer_events
        where wallet_address = ?
        order by block_number, transaction_index, log_index
        """,
        [WALLET_ADDRESS],
    )
    if not events:
        raise RuntimeError("The public demo snapshot cannot be empty")
    if len({(row["chain_id"], row["transaction_hash"], row["log_index"]) for row in events}) != len(events):
        raise RuntimeError("The public demo snapshot contains duplicate event identities")
    validate_snapshot_events(snapshot, events)
    return snapshot, events


def validate_snapshot_events(snapshot: dict[str, Any], events: list[dict[str, Any]]) -> None:
    cumulative_event_count = snapshot.get("cumulative_event_count")
    if not isinstance(cumulative_event_count, int) or cumulative_event_count != len(events):
        raise RuntimeError("Snapshot event rows do not match cumulative pipeline metadata")
    start_block = snapshot["snapshot_start_block"]
    end_block = snapshot["snapshot_end_block"]
    if any(not start_block <= row["block_number"] <= end_block for row in events):
        raise RuntimeError("Snapshot contains an event outside the completed finalized interval")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-db", type=Path, required=True)
    args = parser.parse_args()

    import duckdb

    connection = duckdb.connect(str(args.source_db), read_only=True)
    try:
        snapshot, events = load_snapshot(connection)
    finally:
        connection.close()

    rpc_url = resolved_runtime()["ethereum_rpc_url"]
    if not rpc_url:
        raise SystemExit("ETHEREUM_RPC_URL is required to generate pinned enrichment evidence")
    client = JsonRpcClient(str(rpc_url))
    if int(client.call("eth_chainId", []), 16) != 1:
        raise RuntimeError("Mainnet demo generation requires an Ethereum mainnet RPC")

    snapshot_block_tag = hex(snapshot["snapshot_end_block"])
    snapshot_block = client.call("eth_getBlockByNumber", [snapshot_block_tag, False])
    if (
        not isinstance(snapshot_block, dict)
        or str(snapshot_block.get("hash", "")).lower() != snapshot["snapshot_end_block_hash"]
    ):
        raise RuntimeError("RPC canonical block hash does not match the completed finalized snapshot")

    enrichment_block_tag, enrichment_block, enrichment_finality_policy = resolve_observation_block(client)

    token_addresses = sorted({row["token_address"] for row in events})
    token_rows = fetch_metadata(client, token_addresses, enrichment_block_tag)
    failed_tokens = [row["token_address"] for row in token_rows if row["fetch_status"] == "failed"]
    if failed_tokens:
        raise RuntimeError(f"Token metadata collection failed for {len(failed_tokens)} contracts")
    counterparty_addresses = sorted(
        {
            row["to_address"] if row["from_address"] == WALLET_ADDRESS else row["from_address"]
            for row in events
        }
        - {WALLET_ADDRESS, ZERO_ADDRESS}
    )
    code_results = fetch_code_batch(client, counterparty_addresses, enrichment_block_tag)
    account_rows = build_evidence_rows(
        counterparty_addresses,
        code_results,
        enrichment_block,
        enrichment_finality_policy,
    )
    failed_accounts = [row["address"] for row in account_rows if row["fetch_status"] != "complete"]
    if failed_accounts:
        raise RuntimeError(f"Counterparty evidence is incomplete for {len(failed_accounts)} addresses")

    snapshot_row = {
        **snapshot,
        "snapshot_source": "envio_hyperindex",
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "wallet_attribution_source_url": ATTRIBUTION_SOURCE_URL,
    }
    manifest = {
        **normalized_row(snapshot_row, SNAPSHOT_COLUMNS),
        "wallet_label": WALLET_LABEL,
        "event_count": len(events),
        "token_contract_count": len(token_addresses),
        "counterparty_count": len(counterparty_addresses),
        "event_block_number_min": min(row["block_number"] for row in events),
        "event_block_number_max": max(row["block_number"] for row in events),
        "event_timestamp_min": datetime.fromtimestamp(
            min(row["block_timestamp"] for row in events), timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "event_timestamp_max": datetime.fromtimestamp(
            max(row["block_timestamp"] for row in events), timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "enrichment_observation_block_number": int(enrichment_block["number"], 16),
        "enrichment_observation_block_hash": str(enrichment_block["hash"]).lower(),
        "enrichment_observation_block_timestamp": datetime.fromtimestamp(
            int(enrichment_block["timestamp"], 16), timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "enrichment_finality_policy": enrichment_finality_policy,
        "capture_scope": "Transfer(address,address,uint256) logs involving the configured wallet",
        "sampling": "none",
    }

    write_csv(SEED_DIR / "raw_transfer_events_demo.csv", EVENT_COLUMNS, events)
    write_csv(SEED_DIR / "token_rpc_metadata_demo.csv", TOKEN_COLUMNS, token_rows)
    write_csv(SEED_DIR / "account_evidence_demo.csv", ACCOUNT_COLUMNS, account_rows)
    write_csv(SEED_DIR / "demo_snapshot.csv", SNAPSHOT_COLUMNS, [snapshot_row])
    write_csv(
        SEED_DIR / "wallets_demo.csv",
        ("ens", "address"),
        [{"ens": WALLET_LABEL, "address": WALLET_ADDRESS}],
    )
    write_json(SEED_DIR / "demo_snapshot_manifest.json", manifest)
    print(
        f"Wrote finalized mainnet demo: events={len(events)}, tokens={len(token_addresses)}, "
        f"counterparties={len(counterparty_addresses)}, end_block={snapshot['snapshot_end_block']}"
    )


if __name__ == "__main__":
    main()
