#!/usr/bin/env python3
"""Read self-declared ERC20 metadata for high-impact unverified contracts."""

from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from .project_config import resolved_runtime
except ImportError:
    from project_config import resolved_runtime


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "analytics" / "wallet_analytics.duckdb"
REQUIREMENTS = ROOT / "analytics" / "requirements.txt"
OUTPUT_PATH = ROOT / "analytics" / "seeds" / "token_rpc_metadata.csv"
FIELDNAMES = [
    "token_address",
    "name",
    "symbol",
    "decimals",
    "rpc_block_number",
    "fetched_at",
    "fetch_status",
    "error_code",
]
METHOD_SELECTORS = {
    "name": "0x06fdde03",
    "symbol": "0x95d89b41",
    "decimals": "0x313ce567",
}


def ensure_dependencies() -> None:
    if all(importlib.util.find_spec(module) is not None for module in ("duckdb", "eth_abi")):
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)], check=True)


def clean_text(value: str) -> str | None:
    normalized = " ".join(value.replace("\x00", "").split()).strip()
    if not normalized or len(normalized) > 128:
        return None
    if any(ord(character) < 32 for character in normalized):
        return None
    return normalized


def decode_text_result(value: str | None) -> str | None:
    if not value or value == "0x":
        return None
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        return None
    try:
        from eth_abi import decode

        decoded = decode(["string"], raw)[0]
        return clean_text(decoded)
    except Exception:
        if len(raw) != 32:
            return None
        try:
            return clean_text(raw.rstrip(b"\x00").decode("utf-8"))
        except UnicodeDecodeError:
            return None


def decode_decimals_result(value: str | None) -> int | None:
    if not value or value == "0x":
        return None
    try:
        raw = bytes.fromhex(value.removeprefix("0x"))
    except ValueError:
        return None
    if not raw or len(raw) > 32:
        return None
    decimals = int.from_bytes(raw, "big")
    return decimals if 0 <= decimals <= 255 else None


class JsonRpcClient:
    def __init__(
        self,
        url: str,
        transport: Callable[[str, Any], Any] | None = None,
        retries: int = 3,
    ) -> None:
        self.url = url
        self.transport = transport or self._http_transport
        self.retries = retries
        self.next_id = 1

    @staticmethod
    def _http_transport(url: str, payload: Any) -> Any:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", "User-Agent": "evm-wallet-search/0.1"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.load(response)

    def send(self, payload: Any) -> Any:
        for attempt in range(self.retries):
            try:
                return self.transport(self.url, payload)
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
                if attempt + 1 == self.retries:
                    raise
                time.sleep(2**attempt)
        raise RuntimeError("RPC request exhausted retries")

    def call(self, method: str, params: list[Any]) -> Any:
        request_id = self.next_id
        self.next_id += 1
        response = self.send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        if not isinstance(response, dict) or response.get("id") != request_id:
            raise RuntimeError(f"RPC {method} returned an invalid response")
        error = response.get("error")
        if error:
            code = error.get("code", "unknown") if isinstance(error, dict) else "unknown"
            raise RuntimeError(f"RPC {method} failed: {code}")
        return response.get("result")

    def batch(self, requests: list[tuple[str, list[Any], tuple[str, str]]]) -> dict[tuple[str, str], str | None]:
        payload = []
        keys: dict[int, tuple[str, str]] = {}
        for method, params, key in requests:
            request_id = self.next_id
            self.next_id += 1
            keys[request_id] = key
            payload.append({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        response = self.send(payload)
        if not isinstance(response, list):
            results: dict[tuple[str, str], str | None] = {}
            for method, params, key in requests:
                try:
                    results[key] = self.call(method, params)
                except RuntimeError:
                    results[key] = None
            return results
        by_id = {item.get("id"): item for item in response if isinstance(item, dict)}
        return {
            key: None if by_id.get(request_id, {}).get("error") else by_id.get(request_id, {}).get("result")
            for request_id, key in keys.items()
        }


def read_existing(path: Path = OUTPUT_PATH) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(newline="") as source:
        return {row["token_address"].lower(): row for row in csv.DictReader(source)}


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
            select token_address, count(*) as transfer_count
            from wallet_events
            where token_status = 'unverified'
            group by token_address
            order by transfer_count desc, token_address
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


def fetch_metadata(client: JsonRpcClient, addresses: list[str], block_tag: str) -> list[dict[str, Any]]:
    results: dict[tuple[str, str], str | None] = {}
    calls = [
        ("eth_call", [{"to": address, "data": selector}, block_tag], (address, field))
        for address in addresses
        for field, selector in METHOD_SELECTORS.items()
    ]
    for offset in range(0, len(calls), 60):
        results.update(client.batch(calls[offset : offset + 60]))

    fetched_at = datetime.now(timezone.utc).isoformat()
    block_number = int(block_tag, 16)
    rows = []
    for address in addresses:
        name = decode_text_result(results.get((address, "name")))
        symbol = decode_text_result(results.get((address, "symbol")))
        decimals = decode_decimals_result(results.get((address, "decimals")))
        missing = [field for field, value in (("name", name), ("symbol", symbol), ("decimals", decimals)) if value is None]
        status = "complete" if not missing else "failed" if len(missing) == 3 else "partial"
        rows.append(
            {
                "token_address": address,
                "name": name or "",
                "symbol": symbol or "",
                "decimals": "" if decimals is None else decimals,
                "rpc_block_number": block_number,
                "fetched_at": fetched_at,
                "fetch_status": status,
                "error_code": "" if not missing else "missing:" + "|".join(missing),
            }
        )
    return rows


def write_rows(existing: dict[str, dict[str, str]], rows: list[dict[str, Any]], path: Path = OUTPUT_PATH) -> None:
    merged: dict[str, dict[str, Any]] = {**existing}
    merged.update({str(row["token_address"]): row for row in rows})
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
    parser.add_argument("--limit", type=int, default=100)
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
        print("No eligible unverified token contracts found")
        return

    rpc_url = resolved_runtime()["ethereum_rpc_url"]
    if not rpc_url:
        raise SystemExit("No Ethereum RPC URL or public fallback is configured")
    client = JsonRpcClient(rpc_url)
    chain_id = int(client.call("eth_chainId", []), 16)
    if chain_id != 1:
        raise SystemExit(f"Metadata enrichment requires Ethereum mainnet, got chain ID {chain_id}")
    block_tag = client.call("eth_blockNumber", [])
    rows = fetch_metadata(client, addresses, block_tag)
    write_rows(existing, rows)
    counts = {status: sum(row["fetch_status"] == status for row in rows) for status in ("complete", "partial", "failed")}
    print(
        f"Enriched {len(rows)} contracts at block {int(block_tag, 16)}: "
        f"complete={counts['complete']}, partial={counts['partial']}, failed={counts['failed']}"
    )


if __name__ == "__main__":
    main()
