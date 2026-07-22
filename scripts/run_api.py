#!/usr/bin/env python3
"""Run the local live-analytics API on loopback only."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


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


def main() -> None:
    ensure_dependencies()
    prepare_import_path()
    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
