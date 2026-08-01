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

try:
    from .artifact_paths import (
        ACCOUNT_EVIDENCE_DB_PATH,
        ACCOUNT_EVIDENCE_DUCKDB_PATH_ENV,
        ANALYTICS_DIR,
        DBT_DUCKDB_PATH_ENV,
        database_path,
    )
    from .enrich_counterparty_types import ensure_evidence_store
    from .enrich_token_metadata import JsonRpcClient
    from .project_config import resolved_runtime
    from .snapshot_runs import (
        SnapshotAlreadyCurrent,
        dbt_snapshot_environment,
        fetch_hyperindex_metadata,
        finish_snapshot_run,
        latest_completed_snapshot_run,
        read_configured_wallets,
        resolve_snapshot_target,
        start_snapshot_runs,
    )
except ImportError:
    from artifact_paths import (
        ACCOUNT_EVIDENCE_DB_PATH,
        ACCOUNT_EVIDENCE_DUCKDB_PATH_ENV,
        ANALYTICS_DIR,
        DBT_DUCKDB_PATH_ENV,
        database_path,
    )
    from enrich_counterparty_types import ensure_evidence_store
    from enrich_token_metadata import JsonRpcClient
    from project_config import resolved_runtime
    from snapshot_runs import (
        SnapshotAlreadyCurrent,
        dbt_snapshot_environment,
        fetch_hyperindex_metadata,
        finish_snapshot_run,
        latest_completed_snapshot_run,
        read_configured_wallets,
        resolve_snapshot_target,
        start_snapshot_runs,
    )


REQUIREMENTS = ANALYTICS_DIR / "requirements.txt"
HYPERINDEX_DSN_ENV = "DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN"
DBT_DOCS_SUBCOMMANDS = {"generate", "serve"}


def ensure_python_dependencies() -> None:
    """Install dbt-duckdb into the active Python environment when missing."""

    if importlib.util.find_spec("dbt") is not None:
        return

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS)],
        check=True,
    )


def run_dbt(
    command: str,
    extra_args: list[str],
    *,
    use_hyperindex: bool,
    hyperindex_dsn: str | None,
    extra_env: dict[str, str] | None = None,
) -> None:
    """Execute dbt against the database dedicated to the selected source mode."""

    if command == "docs":
        if not extra_args or extra_args[0] not in DBT_DOCS_SUBCOMMANDS:
            supported = ", ".join(sorted(DBT_DOCS_SUBCOMMANDS))
            raise SystemExit(f"dbt docs requires one of these subcommands: {supported}")
        if use_hyperindex:
            raise SystemExit("dbt docs commands support fixture mode only")

    env = os.environ.copy()
    env["DBT_PROFILES_DIR"] = str(ANALYTICS_DIR)
    db_path = database_path(use_fixture=not use_hyperindex)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    env[DBT_DUCKDB_PATH_ENV] = str(db_path)
    env[ACCOUNT_EVIDENCE_DUCKDB_PATH_ENV] = str(ACCOUNT_EVIDENCE_DB_PATH)
    env.update(extra_env or {})
    ensure_evidence_store(ACCOUNT_EVIDENCE_DB_PATH)
    if use_hyperindex:
        if not hyperindex_dsn:
            raise SystemExit(
                f"Live HyperIndex mode requires {HYPERINDEX_DSN_ENV}. "
                "Set it to the Envio Postgres connection URI before running dbt."
            )
        env[HYPERINDEX_DSN_ENV] = hyperindex_dsn
    else:
        # Fixture builds must never attach the live ingestion database implicitly.
        env.pop(HYPERINDEX_DSN_ENV, None)

    dbt_executable = shutil.which("dbt")
    if dbt_executable is None:
        scripts_dir = Path(sys.executable).resolve().parent
        dbt_candidate = scripts_dir / "dbt"
        dbt_executable = str(dbt_candidate)

    if command == "docs":
        # `docs` is a dbt command group, so its generate/serve subcommand must
        # precede the project and profile options accepted by that subcommand.
        command_args = [command, extra_args[0]]
        remaining_args = extra_args[1:]
    else:
        command_args = [command]
        remaining_args = extra_args

    args = [
        dbt_executable,
        *command_args,
        "--project-dir",
        str(ANALYTICS_DIR),
        "--profiles-dir",
        str(ANALYTICS_DIR),
        *remaining_args,
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
    if command not in {"build", "test", "seed", "run", "docs"}:
        raise SystemExit(f"Unsupported dbt command: {command}")

    ensure_python_dependencies()
    runtime = resolved_runtime()
    use_hyperindex = requests_hyperindex(sys.argv[2:])
    hyperindex_dsn = os.environ.get(HYPERINDEX_DSN_ENV) or runtime["hyperindex_postgres_dsn"]
    if use_hyperindex and command == "build":
        if not hyperindex_dsn:
            raise SystemExit(
                f"Live HyperIndex mode requires {HYPERINDEX_DSN_ENV}. "
                "Set it to the Envio Postgres connection URI before running dbt."
            )
        graphql_url = runtime["hyperindex_graphql_url"]
        rpc_url = runtime["ethereum_rpc_url"]
        if not graphql_url or not rpc_url:
            raise SystemExit("Live snapshot builds require HyperIndex GraphQL and Ethereum RPC URLs")
        metadata = fetch_hyperindex_metadata(str(graphql_url))
        finalized_block = resolve_snapshot_target(JsonRpcClient(str(rpc_url)), metadata)
        wallets = read_configured_wallets()
        try:
            snapshot_runs = start_snapshot_runs(
                wallets=wallets,
                metadata=metadata,
                finalized_block=finalized_block,
            )
        except SnapshotAlreadyCurrent as current:
            print(current)
            snapshot_runs = [
                latest_completed_snapshot_run(wallet=wallet, metadata=metadata, finalized_block=finalized_block)
                for wallet in wallets
            ]
            run_dbt(
                command,
                sys.argv[2:],
                use_hyperindex=True,
                hyperindex_dsn=str(hyperindex_dsn),
                extra_env=dbt_snapshot_environment(
                    snapshot_runs[0],
                    coverage_start_block=metadata.start_block,
                ),
            )
            return
        try:
            run_dbt(
                command,
                sys.argv[2:],
                use_hyperindex=True,
                hyperindex_dsn=str(hyperindex_dsn) if hyperindex_dsn else None,
                extra_env=dbt_snapshot_environment(
                    snapshot_runs[0],
                    coverage_start_block=metadata.start_block,
                ),
            )
        except BaseException:
            for snapshot_run in snapshot_runs:
                finish_snapshot_run(snapshot_run, succeeded=False)
            raise
        for snapshot_run in snapshot_runs:
            finish_snapshot_run(snapshot_run, succeeded=True)
        return

    run_dbt(
        command,
        sys.argv[2:],
        use_hyperindex=use_hyperindex,
        hyperindex_dsn=str(hyperindex_dsn) if hyperindex_dsn else None,
    )


if __name__ == "__main__":
    main()
