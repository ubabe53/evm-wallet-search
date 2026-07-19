#!/usr/bin/env python3
"""Collect pinned-block account evidence for ranked Ethereum counterparties."""

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
    from .enrich_token_metadata import JsonRpcClient, ensure_dependencies
    from .project_config import resolved_runtime
except ImportError:
    from enrich_token_metadata import JsonRpcClient, ensure_dependencies
    from project_config import resolved_runtime


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "analytics" / "wallet_analytics.duckdb"
OUTPUT_PATH = ROOT / "analytics" / "seeds" / "counterparty_code_metadata.csv"
MANIFEST_PATH = ROOT / "analytics" / "seeds" / "account_evidence_manifest.json"
EVIDENCE_SCHEMA_VERSION = "account-evidence-v1"
SAFE_METHOD_SELECTORS = {
    "owners": "0xa0e67e2b",
    "threshold": "0xe75235b8",
}
FIELDNAMES = [
    "chain_id",
    "address",
    "account_type",
    "code_state",
    "code_size_bytes",
    "observation_block_number",
    "observation_block_timestamp",
    "eip7702_delegation_target",
    "safe_verified",
    "safe_verification_status",
    "safe_version",
    "safe_singleton_address",
    "safe_owner_count",
    "safe_threshold",
    "erc4337_observed",
    "erc4337_user_operation_count",
    "erc4337_first_observed_block",
    "erc4337_last_observed_block",
    "erc4337_entrypoint_address",
    "erc4337_entrypoint_version",
    "erc4337_entrypoint_source",
    "fetch_status",
    "reason_codes",
    "coverage_scope",
    "coverage_start_block",
    "coverage_end_block",
    "evidence_schema_version",
    "fetched_at",
]


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text())
    if payload.get("schema_version") != EVIDENCE_SCHEMA_VERSION or payload.get("chain_id") != 1:
        raise ValueError("Account evidence manifest must use schema v1 for Ethereum mainnet")
    safe_addresses = [item["address"].lower() for item in payload["safe_singletons"]]
    entrypoint_addresses = [item["address"].lower() for item in payload["erc4337"]["entrypoints"]]
    if len(safe_addresses) != len(set(safe_addresses)) or len(entrypoint_addresses) != len(set(entrypoint_addresses)):
        raise ValueError("Account evidence manifest addresses must be unique")
    if any(len(address) != 42 for address in safe_addresses + entrypoint_addresses):
        raise ValueError("Account evidence manifest contains a malformed address")
    topic = payload["erc4337"]["event_topic"]
    if not isinstance(topic, str) or len(topic) != 66:
        raise ValueError("Account evidence manifest contains a malformed event topic")
    return payload


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
        eligible = [address for address in ranked if existing.get(address, {}).get("fetch_status") in ("failed", "partial")]
    else:
        eligible = [address for address in ranked if address not in existing]
    return eligible[:limit]


def decode_code(value: str | None) -> tuple[str, int | None, str | None, str, str]:
    """Decode raw account code without treating arbitrary 23-byte code as EIP-7702."""

    if value is None:
        return "unknown", None, None, "failed", "code_lookup_missing"
    normalized = value.removeprefix("0x")
    try:
        raw = bytes.fromhex(normalized)
    except ValueError:
        return "unknown", None, None, "failed", "code_lookup_malformed"
    if not raw:
        return "no_code", 0, None, "complete", "no_code_observed"
    if len(raw) == 23 and raw[:3] == bytes.fromhex("ef0100"):
        return "eip7702_delegated", 23, "0x" + raw[3:].hex(), "complete", "eip7702_delegation_observed"
    return "contract_code", len(raw), None, "complete", "contract_code_observed"


def decode_storage_address(value: str | None) -> str | None:
    if not value or value == "0x":
        return None
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        return None
    if len(raw) != 32 or any(raw[:12]):
        return None
    return "0x" + raw[12:].hex()


def decode_uint256(value: str | None) -> int | None:
    if not value or value == "0x":
        return None
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        return None
    return int.from_bytes(raw, "big") if len(raw) == 32 else None


def decode_address_array(value: str | None) -> list[str] | None:
    if not value or value == "0x":
        return None
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        return None
    if len(raw) < 64:
        return None
    offset = int.from_bytes(raw[:32], "big")
    if offset + 32 > len(raw) or offset % 32:
        return None
    count = int.from_bytes(raw[offset : offset + 32], "big")
    start = offset + 32
    end = start + count * 32
    if end != len(raw):
        return None
    owners = []
    for position in range(start, end, 32):
        word = raw[position : position + 32]
        if any(word[:12]) or not any(word[12:]):
            return None
        owners.append("0x" + word[12:].hex())
    return owners


def safe_evidence(
    singleton_address: str | None,
    owners_result: str | None,
    threshold_result: str | None,
    safe_singletons: dict[str, dict[str, str]],
) -> dict[str, Any]:
    singleton = singleton_address.lower() if singleton_address else None
    deployment = safe_singletons.get(singleton or "")
    if deployment is None:
        return {
            "safe_verified": False,
            "safe_verification_status": "singleton_not_official",
            "safe_version": "",
            "safe_singleton_address": singleton or "",
            "safe_owner_count": "",
            "safe_threshold": "",
            "reason": "safe_singleton_not_official",
        }

    owners = decode_address_array(owners_result)
    threshold = decode_uint256(threshold_result)
    consistent = (
        owners is not None
        and len(owners) > 0
        and len(set(owners)) == len(owners)
        and threshold is not None
        and 1 <= threshold <= len(owners)
    )
    return {
        "safe_verified": consistent,
        "safe_verification_status": "verified" if consistent else "calls_inconsistent",
        "safe_version": deployment["version"] if consistent else "",
        "safe_singleton_address": singleton or "",
        "safe_owner_count": len(owners) if owners is not None else "",
        "safe_threshold": threshold if threshold is not None else "",
        "reason": "safe_verified" if consistent else "safe_calls_inconsistent",
    }


def sender_topic(address: str) -> str:
    return "0x" + address.lower().removeprefix("0x").rjust(64, "0")


def fetch_erc4337_evidence(
    client: JsonRpcClient,
    addresses: list[str],
    start_block: int,
    end_block: int,
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    event_topic = manifest["erc4337"]["event_topic"]
    entrypoints = manifest["erc4337"]["entrypoints"]
    calls = [
        (
            "eth_getLogs",
            [{
                "address": entrypoint["address"],
                "fromBlock": hex(start_block),
                "toBlock": hex(end_block),
                "topics": [event_topic, None, sender_topic(address)],
            }],
            (address, f"erc4337:{entrypoint['version']}"),
        )
        for address in addresses
        for entrypoint in entrypoints
    ]
    results: dict[tuple[str, str], Any] = {}
    for offset in range(0, len(calls), 40):
        results.update(client.batch(calls[offset : offset + 40]))

    evidence: dict[str, dict[str, Any]] = {}
    for address in addresses:
        matched: list[tuple[dict[str, str], dict[str, Any]]] = []
        complete = True
        for entrypoint in entrypoints:
            logs = results.get((address, f"erc4337:{entrypoint['version']}"))
            if logs is None:
                complete = False
                continue
            if not isinstance(logs, list):
                complete = False
                continue
            matched.extend((entrypoint, log) for log in logs if isinstance(log, dict))

        blocks = [int(log["blockNumber"], 16) for _entrypoint, log in matched if log.get("blockNumber")]
        matched_entrypoints = sorted(
            {entrypoint["address"].lower(): entrypoint for entrypoint, _log in matched}.values(),
            key=lambda item: item["version"],
        )
        evidence[address] = {
            "observed": bool(matched),
            "complete": complete,
            "count": len(matched),
            "first_block": min(blocks) if blocks else "",
            "last_block": max(blocks) if blocks else "",
            "addresses": "|".join(item["address"].lower() for item in matched_entrypoints),
            "versions": "|".join(item["version"] for item in matched_entrypoints),
            "sources": "|".join(item["source_url"] for item in matched_entrypoints),
        }
    return evidence


def fetch_account_evidence(
    client: JsonRpcClient,
    addresses: list[str],
    block_tag: str,
    block_timestamp: str,
    coverage_start_block: int,
    manifest: dict[str, Any],
) -> list[dict[str, Any]]:
    code_calls = [("eth_getCode", [address, block_tag], (address, "code")) for address in addresses]
    code_results: dict[tuple[str, str], Any] = {}
    for offset in range(0, len(code_calls), 100):
        code_results.update(client.batch(code_calls[offset : offset + 100]))

    decoded = {address: decode_code(code_results.get((address, "code"))) for address in addresses}
    code_addresses = [address for address, values in decoded.items() if values[0] in ("contract_code", "eip7702_delegated")]
    safe_calls = [
        ("eth_getStorageAt", [address, "0x0", block_tag], (address, "singleton"))
        for address in code_addresses
        if decoded[address][0] == "contract_code"
    ] + [
        ("eth_call", [{"to": address, "data": selector}, block_tag], (address, field))
        for address in code_addresses
        for field, selector in SAFE_METHOD_SELECTORS.items()
    ]
    safe_results: dict[tuple[str, str], Any] = {}
    for offset in range(0, len(safe_calls), 60):
        safe_results.update(client.batch(safe_calls[offset : offset + 60]))

    observation_block = int(block_tag, 16)
    erc4337 = fetch_erc4337_evidence(
        client,
        addresses,
        coverage_start_block,
        observation_block,
        manifest,
    )
    safe_singletons = {item["address"].lower(): item for item in manifest["safe_singletons"]}
    fetched_at = datetime.now(timezone.utc).isoformat()
    rows = []
    for address in addresses:
        code_state, code_size, delegation_target, code_status, code_reason = decoded[address]
        reasons = [code_reason]
        if code_state == "contract_code":
            singleton = decode_storage_address(safe_results.get((address, "singleton")))
            safe = safe_evidence(
                singleton,
                safe_results.get((address, "owners")),
                safe_results.get((address, "threshold")),
                safe_singletons,
            )
            if safe_results.get((address, "singleton")) is None:
                safe["safe_verification_status"] = "evidence_unavailable"
                safe["reason"] = "safe_evidence_unavailable"
        elif code_state == "eip7702_delegated":
            safe = safe_evidence(
                delegation_target,
                safe_results.get((address, "owners")),
                safe_results.get((address, "threshold")),
                safe_singletons,
            )
        else:
            safe = {
                "safe_verified": False,
                "safe_verification_status": "not_applicable" if code_state == "no_code" else "not_checked",
                "safe_version": "",
                "safe_singleton_address": "",
                "safe_owner_count": "",
                "safe_threshold": "",
                "reason": "safe_not_applicable" if code_state == "no_code" else "safe_not_checked",
            }
        reasons.append(safe.pop("reason"))

        erc = erc4337[address]
        reasons.append(
            "erc4337_sender_observed"
            if erc["observed"]
            else "erc4337_sender_not_observed"
            if erc["complete"]
            else "erc4337_evidence_unavailable"
        )
        if code_state == "eip7702_delegated":
            account_type = "eip7702_delegated"
        elif safe["safe_verified"]:
            account_type = "safe"
        elif erc["observed"]:
            account_type = "erc4337_account"
        elif code_state == "contract_code":
            account_type = "contract"
        elif code_state == "no_code":
            account_type = "eoa_candidate"
        else:
            account_type = "unknown"

        status = code_status
        if status == "complete" and (
            not erc["complete"] or safe["safe_verification_status"] in ("evidence_unavailable", "calls_inconsistent")
        ):
            status = "partial"
        rows.append(
            {
                "chain_id": 1,
                "address": address,
                "account_type": account_type,
                "code_state": code_state,
                "code_size_bytes": "" if code_size is None else code_size,
                "observation_block_number": observation_block,
                "observation_block_timestamp": block_timestamp,
                "eip7702_delegation_target": delegation_target or "",
                **safe,
                "erc4337_observed": erc["observed"],
                "erc4337_user_operation_count": erc["count"],
                "erc4337_first_observed_block": erc["first_block"],
                "erc4337_last_observed_block": erc["last_block"],
                "erc4337_entrypoint_address": erc["addresses"],
                "erc4337_entrypoint_version": erc["versions"],
                "erc4337_entrypoint_source": erc["sources"],
                "fetch_status": status,
                "reason_codes": "|".join(sorted(set(reasons))),
                "coverage_scope": "ranked_counterparties",
                "coverage_start_block": coverage_start_block,
                "coverage_end_block": observation_block,
                "evidence_schema_version": EVIDENCE_SCHEMA_VERSION,
                "fetched_at": fetched_at,
            }
        )
    return rows


def write_rows(existing: dict[str, dict[str, str]], rows: list[dict[str, Any]], path: Path = OUTPUT_PATH) -> None:
    merged: dict[str, dict[str, Any]] = {**existing}
    merged.update({str(row["address"]).lower(): row for row in rows})
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(merged[address] for address in sorted(merged))
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--erc4337-start-block",
        type=int,
        help="First block checked for canonical EntryPoint sender evidence; defaults to the indexed event start",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--retry-failed", action="store_true")
    mode.add_argument("--refresh", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit <= 0:
        raise SystemExit("--limit must be positive")
    if args.erc4337_start_block is not None and args.erc4337_start_block < 0:
        raise SystemExit("--erc4337-start-block cannot be negative")
    ensure_dependencies()
    import duckdb

    if not DB_PATH.exists():
        raise SystemExit("Analytics database is missing; run an analytics build first")
    existing = read_existing()
    connection = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        addresses = select_candidates(connection, existing, args.limit, args.retry_failed, args.refresh)
        indexed_start_block = connection.execute("select min(block_number) from wallet_events").fetchone()[0]
    finally:
        connection.close()
    if not addresses:
        print("No eligible counterparty addresses found")
        return

    runtime = resolved_runtime()
    rpc_url = runtime["ethereum_rpc_url"]
    if not rpc_url:
        raise SystemExit("No Ethereum RPC URL or public fallback is configured")
    configured_start = runtime.get("account_evidence_start_block")
    coverage_start_block = (
        args.erc4337_start_block
        if args.erc4337_start_block is not None
        else int(configured_start)
        if configured_start is not None
        else int(indexed_start_block)
    )
    client = JsonRpcClient(rpc_url)
    chain_id = int(client.call("eth_chainId", []), 16)
    if chain_id != 1:
        raise SystemExit(f"Account enrichment requires Ethereum mainnet, got chain ID {chain_id}")
    block_tag = client.call("eth_blockNumber", [])
    block = client.call("eth_getBlockByNumber", [block_tag, False])
    if not isinstance(block, dict) or block.get("number") != block_tag or not block.get("timestamp"):
        raise SystemExit("Could not read the pinned Ethereum block timestamp")
    block_timestamp = datetime.fromtimestamp(int(block["timestamp"], 16), timezone.utc).isoformat()
    observation_block = int(block_tag, 16)
    if coverage_start_block > observation_block:
        raise SystemExit(
            f"ERC-4337 coverage start block {coverage_start_block} exceeds pinned block {observation_block}"
        )
    manifest = load_manifest()
    rows = fetch_account_evidence(
        client,
        addresses,
        block_tag,
        block_timestamp,
        coverage_start_block,
        manifest,
    )
    write_rows(existing, rows)
    counts = {status: sum(row["fetch_status"] == status for row in rows) for status in ("complete", "partial", "failed")}
    print(
        f"Collected account evidence for {len(rows)} addresses at block {int(block_tag, 16)}: "
        f"complete={counts['complete']}, partial={counts['partial']}, failed={counts['failed']}"
    )


if __name__ == "__main__":
    main()
