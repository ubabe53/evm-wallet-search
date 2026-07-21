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


def main() -> None:
    ensure_dependencies()
    import uvicorn

    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
