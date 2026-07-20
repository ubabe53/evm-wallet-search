#!/usr/bin/env python3
"""Run dbt commands with the project's local profile and dependency bootstrap.

The JavaScript entrypoints stay under Bun, while dbt remains a Python tool.
This wrapper keeps the user-facing command simple: `bun run analytics:build`.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

from project_config import resolved_runtime


ROOT = Path(__file__).resolve().parents[1]
ANALYTICS_DIR = ROOT / "analytics"
REQUIREMENTS = ANALYTICS_DIR / "requirements.txt"
HYPERINDEX_DSN_ENV = "DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN"


def ensure_python_dependencies() -> None:
    """Install dbt-duckdb into the active Python environment when missing."""

    if importlib.util.find_spec("dbt") is not None:
        return

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        check=True,
    )


def run_dbt(command: str, extra_args: list[str]) -> None:
    """Execute dbt from the analytics project with snapshot mode enabled by default."""

    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = str(ANALYTICS_DIR)

    dbt_executable = shutil.which("dbt")
    if dbt_executable is None:
        scripts_dir = Path(sys.executable).resolve().parent
        dbt_candidate = scripts_dir / "dbt"
        dbt_executable = str(dbt_candidate)

    args = [
        dbt_executable,
        command,
        "--project-dir",
        str(ANALYTICS_DIR),
        "--profiles-dir",
        str(ANALYTICS_DIR),
        *extra_args,
    ]
    subprocess.run(args, check=True, cwd=ANALYTICS_DIR, env=env)


def requests_hyperindex(extra_args: list[str]) -> bool:
    """Return whether dbt vars explicitly disable the fixture source."""

    import yaml

    for index, argument in enumerate(extra_args):
        payload = None
        if argument == "--vars" and index + 1 < len(extra_args):
            payload = extra_args[index + 1]
        elif argument.startswith("--vars="):
            payload = argument.split("=", 1)[1]

        if payload:
            parsed = yaml.safe_load(payload)
            if isinstance(parsed, dict) and parsed.get("use_fixture") is False:
                return True

    return False


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command not in {"build", "test", "seed", "run"}:
        raise SystemExit(f"Unsupported dbt command: {command}")

    ensure_python_dependencies()
    runtime = resolved_runtime()
    if runtime["hyperindex_postgres_dsn"] and not os.environ.get(HYPERINDEX_DSN_ENV):
        os.environ[HYPERINDEX_DSN_ENV] = str(runtime["hyperindex_postgres_dsn"])
    if requests_hyperindex(sys.argv[2:]) and not os.environ.get(HYPERINDEX_DSN_ENV):
        raise SystemExit(
            f"Live HyperIndex mode requires {HYPERINDEX_DSN_ENV}. "
            "Set it to the Envio Postgres connection URI before running dbt."
        )
    run_dbt(command, sys.argv[2:])


if __name__ == "__main__":
    main()
