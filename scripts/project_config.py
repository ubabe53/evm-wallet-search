"""Load shared local configuration without exposing secrets in tracked files."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
PUBLIC_RPC_FALLBACK = "https://ethereum-rpc.publicnode.com"


def load_config(path: Path | None = None) -> dict[str, Any]:
    try:
        import yaml
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "PyYAML>=6,<7"], check=True)
        import yaml

    config_path = path or Path(os.environ.get("EVM_WALLET_CONFIG", DEFAULT_CONFIG_PATH))
    if not config_path.exists():
        return {}
    payload = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Project config must contain a YAML mapping: {config_path}")
    return payload


def nested_value(config: Mapping[str, Any], *keys: str) -> str | None:
    value: Any = config
    for key in keys:
        if not isinstance(value, Mapping):
            return None
        value = value.get(key)
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def configured_value(
    env_name: str,
    config: Mapping[str, Any],
    *config_keys: str,
    default: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> str | None:
    environment = environ if environ is not None else os.environ
    env_value = environment.get(env_name, "").strip()
    return env_value or nested_value(config, *config_keys) or default


def resolved_runtime(config: Mapping[str, Any] | None = None) -> dict[str, str | None]:
    values = config if config is not None else load_config()
    return {
        "envio_api_token": configured_value("ENVIO_API_TOKEN", values, "envio", "api_token"),
        "hyperindex_postgres_dsn": configured_value(
            "DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN",
            values,
            "analytics",
            "hyperindex_postgres_dsn",
        ),
        "ethereum_rpc_url": configured_value(
            "ETHEREUM_RPC_URL",
            values,
            "ethereum",
            "rpc_url",
            default=nested_value(values, "ethereum", "public_rpc_url") or PUBLIC_RPC_FALLBACK,
        ),
        "account_evidence_start_block": configured_value(
            "ACCOUNT_EVIDENCE_START_BLOCK",
            values,
            "ethereum",
            "account_evidence",
            "erc4337_start_block",
        ),
    }
