#!/usr/bin/env python3
"""Synchronize a reproducible Ethereum token recognition snapshot.

Normal analytics builds never call the network. Run this script explicitly to
refresh the checked-in registry from Trust Wallet, Uniswap, CoinGecko, and
Coinbase Exchange.
"""

from __future__ import annotations

import csv
import json
import os
import re
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SEED_PATH = ROOT / "analytics" / "seeds" / "token_metadata.csv"
MANIFEST_PATH = ROOT / "analytics" / "seeds" / "token_metadata_manifest.json"
TRUST_URL = "https://raw.githubusercontent.com/trustwallet/assets/master/blockchains/ethereum/tokenlist.json"
TRUST_COMMIT_URL = "https://api.github.com/repos/trustwallet/assets/commits/master"
UNISWAP_URL = "https://tokens.uniswap.org/"
COINGECKO_URL = "https://tokens.coingecko.com/ethereum/all.json"
COINBASE_URL = "https://api.exchange.coinbase.com/currencies"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")
FIELDNAMES = [
    "token_address",
    "symbol",
    "name",
    "decimals",
    "token_status",
    "recognition_status",
    "metadata_source",
    "metadata_source_url",
]


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "evm-wallet-search/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def normalize_tokens(
    payload: dict[str, Any],
    source: str,
    default_chain_id: int | None = None,
) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    for token in payload.get("tokens", []):
        if token.get("chainId", default_chain_id) != 1:
            continue
        address = str(token.get("address", "")).lower()
        if not ADDRESS_PATTERN.fullmatch(address):
            raise ValueError(f"Invalid Ethereum address from {source}: {address}")
        decimals = int(token["decimals"])
        if not 0 <= decimals <= 255:
            raise ValueError(f"Invalid decimals for {address} from {source}: {decimals}")
        normalized[address] = {
            "token_address": address,
            "symbol": str(token["symbol"]).strip(),
            "name": str(token["name"]).strip(),
            "decimals": decimals,
        }
    return normalized


def normalize_coinbase_currencies(payload: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Return online Coinbase Exchange assets with an exact Ethereum contract.

    Coinbase's currency precision is a trading precision, not ERC-20 decimals,
    so Coinbase-only entries intentionally leave decimals unknown.
    """

    normalized: dict[str, dict[str, Any]] = {}
    for currency in payload:
        if currency.get("status") != "online" or currency.get("details", {}).get("type") != "crypto":
            continue
        for network in currency.get("supported_networks", []):
            if str(network.get("name", "")).lower() != "ethereum" or network.get("status") != "online":
                continue
            address = str(network.get("contract_address", "")).lower()
            if address in {"", "none"}:
                continue
            if not ADDRESS_PATTERN.fullmatch(address):
                raise ValueError(f"Invalid Ethereum address from coinbase: {address}")
            token = {
                "token_address": address,
                "symbol": str(currency["id"]).strip(),
                "name": str(currency["name"]).strip(),
                "decimals": None,
            }
            existing = normalized.get(address)
            if existing and existing != token:
                raise ValueError(f"Conflicting Coinbase currencies for {address}")
            normalized[address] = token
    return normalized


def merge_registries(
    trust_tokens: dict[str, dict[str, Any]],
    uniswap_tokens: dict[str, dict[str, Any]],
    coingecko_tokens: dict[str, dict[str, Any]] | None = None,
    coinbase_tokens: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    coingecko_tokens = coingecko_tokens or {}
    coinbase_tokens = coinbase_tokens or {}
    rows: list[dict[str, Any]] = []
    for address in sorted(
        trust_tokens.keys() | uniswap_tokens.keys() | coingecko_tokens.keys() | coinbase_tokens.keys()
    ):
        trust = trust_tokens.get(address)
        uniswap = uniswap_tokens.get(address)
        coingecko = coingecko_tokens.get(address)
        coinbase = coinbase_tokens.get(address)
        candidates = [token for token in (trust, uniswap, coingecko, coinbase) if token]
        decimals = {token["decimals"] for token in candidates if token["decimals"] is not None}
        if len(decimals) > 1:
            raise ValueError(
                f"Conflicting decimals for {address}: "
                f"Trust Wallet={trust and trust['decimals']}, "
                f"Uniswap={uniswap and uniswap['decimals']}, "
                f"CoinGecko={coingecko and coingecko['decimals']}, "
                f"Coinbase={coinbase and coinbase['decimals']}"
            )
        preferred = trust or uniswap or coingecko or coinbase
        assert preferred is not None
        sources = []
        urls = []
        if trust:
            sources.append("trustwallet")
            urls.append(TRUST_URL)
        if uniswap:
            sources.append("uniswap")
            urls.append(UNISWAP_URL)
        if coingecko:
            sources.append("coingecko")
            urls.append(COINGECKO_URL)
        if coinbase:
            sources.append("coinbase")
            urls.append(COINBASE_URL)
        rows.append(
            {
                **preferred,
                "token_status": "trusted",
                "recognition_status": "recognized",
                "metadata_source": "+".join(sources),
                "metadata_source_url": "|".join(urls),
            }
        )
    return rows


def write_snapshot(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    csv_descriptor, csv_name = tempfile.mkstemp(dir=SEED_PATH.parent, prefix=f".{SEED_PATH.name}.")
    manifest_descriptor, manifest_name = tempfile.mkstemp(
        dir=MANIFEST_PATH.parent,
        prefix=f".{MANIFEST_PATH.name}.",
    )
    csv_path = Path(csv_name)
    manifest_path = Path(manifest_name)
    try:
        with os.fdopen(csv_descriptor, "w", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=FIELDNAMES, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
            output.flush()
            os.fsync(output.fileno())
        with os.fdopen(manifest_descriptor, "w") as output:
            output.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
            output.flush()
            os.fsync(output.fileno())
        csv_path.replace(SEED_PATH)
        manifest_path.replace(MANIFEST_PATH)
    except BaseException:
        csv_path.unlink(missing_ok=True)
        manifest_path.unlink(missing_ok=True)
        raise


def main() -> None:
    trust_payload = fetch_json(TRUST_URL)
    uniswap_payload = fetch_json(UNISWAP_URL)
    coingecko_payload = fetch_json(COINGECKO_URL)
    coinbase_payload = fetch_json(COINBASE_URL)
    trust_commit = fetch_json(TRUST_COMMIT_URL)["sha"]
    trust_tokens = normalize_tokens(trust_payload, "trustwallet", default_chain_id=1)
    uniswap_tokens = normalize_tokens(uniswap_payload, "uniswap")
    coingecko_tokens = normalize_tokens(coingecko_payload, "coingecko")
    coinbase_tokens = normalize_coinbase_currencies(coinbase_payload)
    rows = merge_registries(trust_tokens, uniswap_tokens, coingecko_tokens, coinbase_tokens)
    manifest = {
        "chain_id": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "entry_count": len(rows),
        "sources": {
            "trustwallet": {
                "url": TRUST_URL,
                "commit_sha": trust_commit,
                "entry_count": len(trust_tokens),
            },
            "uniswap": {
                "url": UNISWAP_URL,
                "version": uniswap_payload.get("version"),
                "entry_count": len(uniswap_tokens),
            },
            "coingecko": {
                "url": COINGECKO_URL,
                "version": coingecko_payload.get("version"),
                "timestamp": coingecko_payload.get("timestamp"),
                "entry_count": len(coingecko_tokens),
            },
            "coinbase": {
                "url": COINBASE_URL,
                "entry_count": len(coinbase_tokens),
                "qualification": "online currency with online Ethereum network and exact contract address",
            },
        },
    }
    write_snapshot(rows, manifest)
    print(f"Wrote {len(rows)} Ethereum token labels to {SEED_PATH}")


if __name__ == "__main__":
    main()
