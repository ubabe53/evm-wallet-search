#!/usr/bin/env python3
"""Run the local live-analytics API on loopback only."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "analytics" / "requirements.txt"


def ensure_dependencies() -> None:
    if all(importlib.util.find_spec(module) is not None for module in ("fastapi", "uvicorn", "duckdb")):
        return
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)], check=True)


def prepare_import_path() -> None:
    """Make the repository package importable when this script is executed by path."""

    root = str(ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def bind_host(environment: Mapping[str, str] = os.environ) -> str:
    """Use loopback natively and an explicit all-interface bind only in containers."""

    host = environment.get("EVM_WALLET_API_HOST", "127.0.0.1").strip()
    if host not in {"127.0.0.1", "0.0.0.0"}:
        raise RuntimeError("EVM_WALLET_API_HOST must be 127.0.0.1 or 0.0.0.0")
    return host


def main() -> None:
    ensure_dependencies()
    prepare_import_path()
    import uvicorn

    uvicorn.run("server.app:app", host=bind_host(), port=8000, reload=False)


if __name__ == "__main__":
    main()
