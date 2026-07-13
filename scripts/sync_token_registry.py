#!/usr/bin/env python3
"""Synchronize a reproducible Ethereum token metadata snapshot.

Normal analytics builds never call the network. Run this script explicitly to
refresh the checked-in registry from Trust Wallet, Uniswap, and CoinGecko.
"""

from __future__ import annotations

import csv
import json
import re
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
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")
FIELDNAMES = [
    "token_address",
    "symbol",
    "name",
    "decimals",
    "token_status",
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


def merge_registries(
    trust_tokens: dict[str, dict[str, Any]],
    uniswap_tokens: dict[str, dict[str, Any]],
    coingecko_tokens: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    coingecko_tokens = coingecko_tokens or {}
    rows: list[dict[str, Any]] = []
    for address in sorted(trust_tokens.keys() | uniswap_tokens.keys() | coingecko_tokens.keys()):
        trust = trust_tokens.get(address)
        uniswap = uniswap_tokens.get(address)
        coingecko = coingecko_tokens.get(address)
        candidates = [token for token in (trust, uniswap, coingecko) if token]
        decimals = {token["decimals"] for token in candidates}
        if len(decimals) > 1:
            raise ValueError(
                f"Conflicting decimals for {address}: "
                f"Trust Wallet={trust and trust['decimals']}, "
                f"Uniswap={uniswap and uniswap['decimals']}, "
                f"CoinGecko={coingecko and coingecko['decimals']}"
            )
        preferred = trust or uniswap or coingecko
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
        rows.append(
            {
                **preferred,
                "token_status": "trusted",
                "metadata_source": "+".join(sources),
                "metadata_source_url": "|".join(urls),
            }
        )
    return rows


def write_snapshot(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> None:
    with SEED_PATH.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def main() -> None:
    trust_payload = fetch_json(TRUST_URL)
    uniswap_payload = fetch_json(UNISWAP_URL)
    coingecko_payload = fetch_json(COINGECKO_URL)
    trust_commit = fetch_json(TRUST_COMMIT_URL)["sha"]
    trust_tokens = normalize_tokens(trust_payload, "trustwallet", default_chain_id=1)
    uniswap_tokens = normalize_tokens(uniswap_payload, "uniswap")
    coingecko_tokens = normalize_tokens(coingecko_payload, "coingecko")
    rows = merge_registries(trust_tokens, uniswap_tokens, coingecko_tokens)
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
        },
    }
    write_snapshot(rows, manifest)
    print(f"Wrote {len(rows)} Ethereum token labels to {SEED_PATH}")


if __name__ == "__main__":
    main()
