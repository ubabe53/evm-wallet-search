#!/usr/bin/env python3
"""Run Envio with shared configuration or one isolated bounded scan."""

from __future__ import annotations

import argparse
import copy
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from .project_config import resolved_runtime
except ImportError:
    from project_config import resolved_runtime

ROOT = Path(__file__).resolve().parents[1]
INDEXER_DIR = ROOT / "indexer"
INDEXER_CONFIG = INDEXER_DIR / "config.yaml"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")
SCHEMA_PATTERN = re.compile(r"^wallet_scan_[a-z0-9_]+$")


def bounded_config(*, from_block: int, to_block: int, schema_name: str) -> dict[str, Any]:
    """Return an Envio config restricted to one caller-validated block interval."""

    import yaml

    payload = yaml.safe_load(INDEXER_CONFIG.read_text())
    if not isinstance(payload, dict):
        raise RuntimeError("Indexer config must contain a YAML mapping")
    config = copy.deepcopy(payload)
    chains = config.get("chains")
    if not isinstance(chains, list) or len(chains) != 1 or chains[0].get("id") != 1:
        raise RuntimeError("Bounded scans require exactly one Ethereum mainnet chain config")
    chains[0]["start_block"] = from_block
    chains[0]["end_block"] = to_block
    config["name"] = schema_name.replace("_", "-")
    return config


def run_bounded_scan(arguments: list[str], env: dict[str, str]) -> None:
    parser = argparse.ArgumentParser(prog="run_indexer.py scan")
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--from-block", required=True, type=int)
    parser.add_argument("--to-block", required=True, type=int)
    parser.add_argument("--schema", required=True)
    parser.add_argument("--indexer-port", type=int, default=8082)
    options = parser.parse_args(arguments)

    wallet = options.wallet.strip().lower()
    if not ADDRESS_PATTERN.fullmatch(wallet):
        raise SystemExit("--wallet must be a canonical Ethereum address")
    if options.from_block < 0 or options.to_block < options.from_block:
        raise SystemExit("Bounded scan blocks must satisfy 0 <= from-block <= to-block")
    if not SCHEMA_PATTERN.fullmatch(options.schema):
        raise SystemExit("--schema must use the wallet_scan_<job> namespace")
    if not 1024 <= options.indexer_port <= 65535:
        raise SystemExit("--indexer-port must be between 1024 and 65535")

    env["ENVIO_WALLET_SCAN_ADDRESS"] = wallet
    env["ENVIO_PG_SCHEMA"] = options.schema
    env["ENVIO_INDEXER_PORT"] = str(options.indexer_port)
    config = bounded_config(
        from_block=options.from_block,
        to_block=options.to_block,
        schema_name=options.schema,
    )
    import yaml

    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix="wallet-scan-",
        suffix=".yaml",
        dir=INDEXER_DIR,
    ) as generated:
        yaml.safe_dump(config, generated, sort_keys=False)
        generated.flush()
        subprocess.run(
            ["bunx", "envio", "start", "--restart", "--config", generated.name],
            cwd=INDEXER_DIR,
            env=env,
            check=True,
        )


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if command not in {"dev", "codegen", "scan"}:
        raise SystemExit(f"Unsupported Envio command: {command}")
    env = os.environ.copy()
    token = resolved_runtime()["envio_api_token"]
    if token:
        env["ENVIO_API_TOKEN"] = token
    if command == "scan":
        run_bounded_scan(sys.argv[2:], env)
        return
    subprocess.run(["bunx", "envio", command], cwd=INDEXER_DIR, env=env, check=True)


if __name__ == "__main__":
    main()
