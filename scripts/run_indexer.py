#!/usr/bin/env python3
"""Run Envio with shared project configuration injected into its environment."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from project_config import resolved_runtime

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "dev"
    if command not in {"dev", "codegen"}:
        raise SystemExit(f"Unsupported Envio command: {command}")
    env = os.environ.copy()
    token = resolved_runtime()["envio_api_token"]
    if token:
        env["ENVIO_API_TOKEN"] = token
    subprocess.run(["bunx", "envio", command], cwd=ROOT / "indexer", env=env, check=True)


if __name__ == "__main__":
    main()
