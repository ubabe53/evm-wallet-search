#!/usr/bin/env python3
"""Classify high-activity counterparties by pinned-block Ethereum bytecode."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from .enrich_token_metadata import JsonRpcClient, ensure_dependencies
    from .project_config import resolved_runtime
except ImportError:
    from enrich_token_metadata import JsonRpcClient, ensure_dependencies
    from project_config import resolved_runtime


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "analytics" / "wallet_analytics.duckdb"
OUTPUT_PATH = ROOT / "analytics" / "seeds" / "counterparty_code_metadata.csv"
FIELDNAMES = [
    "address",
    "address_type",
    "code_size_bytes",
    "rpc_block_number",
    "fetched_at",
    "fetch_status",
    "error_code",
]


def read_existing(path: Path = OUTPUT_PATH) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="") as source:
        return {row["address"].lower(): row for row in csv.DictReader(source)}


def select_candidates(
    connection: Any,
    existing: dict[str, dict[str, str]],
    limit: int,
    retry_failed: bool = False,
    refresh: bool = False,
) -> list[str]:
    ranked = [
        row[0]
        for row in connection.execute(
            """
            select counterparty_address, sum(transfer_count) as transfer_count
            from counterparty_summary
            group by counterparty_address
            order by transfer_count desc, counterparty_address
            """
        ).fetchall()
    ]
    if refresh:
        eligible = ranked
    elif retry_failed:
        eligible = [address for address in ranked if existing.get(address, {}).get("fetch_status") == "failed"]
    else:
        eligible = [address for address in ranked if address not in existing]
    return eligible[:limit]


def decode_code(value: str | None) -> tuple[str, int | None, str, str]:
    if value is None:
        return "unknown", None, "failed", "missing:eth_getCode"
    normalized = value.removeprefix("0x")
    if normalized == "":
        return "wallet", 0, "complete", ""
    try:
        raw = bytes.fromhex(normalized)
    except ValueError:
        return "unknown", None, "failed", "malformed:eth_getCode"
    if not raw:
        return "wallet", 0, "complete", ""
    return "contract", len(raw), "complete", ""


def fetch_address_types(client: JsonRpcClient, addresses: list[str], block_tag: str) -> list[dict[str, Any]]:
    calls = [("eth_getCode", [address, block_tag], (address, "code")) for address in addresses]
    results: dict[tuple[str, str], str | None] = {}
    for offset in range(0, len(calls), 100):
        results.update(client.batch(calls[offset : offset + 100]))

    fetched_at = datetime.now(timezone.utc).isoformat()
    block_number = int(block_tag, 16)
    rows = []
    for address in addresses:
        address_type, code_size, fetch_status, error_code = decode_code(results.get((address, "code")))
        rows.append(
            {
                "address": address,
                "address_type": address_type,
                "code_size_bytes": "" if code_size is None else code_size,
                "rpc_block_number": block_number,
                "fetched_at": fetched_at,
                "fetch_status": fetch_status,
                "error_code": error_code,
            }
        )
    return rows


def write_rows(existing: dict[str, dict[str, str]], rows: list[dict[str, Any]], path: Path = OUTPUT_PATH) -> None:
    merged: dict[str, dict[str, Any]] = {**existing}
    merged.update({str(row["address"]): row for row in rows})
    with path.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(merged[address] for address in sorted(merged))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--retry-failed", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    ensure_dependencies()
    import duckdb

    if not DB_PATH.exists():
        raise SystemExit("Analytics database is missing; run an analytics build first")
    existing = read_existing()
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        addresses = select_candidates(connection, existing, args.limit, args.retry_failed, args.refresh)
    finally:
        connection.close()
    if not addresses:
        print("No eligible counterparty addresses found")
        return

    rpc_url = resolved_runtime()["ethereum_rpc_url"]
    if not rpc_url:
        raise SystemExit("No Ethereum RPC URL or public fallback is configured")
    client = JsonRpcClient(rpc_url)
    chain_id = int(client.call("eth_chainId", []), 16)
    if chain_id != 1:
        raise SystemExit(f"Address enrichment requires Ethereum mainnet, got chain ID {chain_id}")
    block_tag = client.call("eth_blockNumber", [])
    rows = fetch_address_types(client, addresses, block_tag)
    write_rows(existing, rows)
    counts = {kind: sum(row["address_type"] == kind for row in rows) for kind in ("contract", "wallet", "unknown")}
    print(
        f"Classified {len(rows)} addresses at block {int(block_tag, 16)}: "
        f"contract={counts['contract']}, wallet={counts['wallet']}, unknown={counts['unknown']}"
    )


if __name__ == "__main__":
    main()
