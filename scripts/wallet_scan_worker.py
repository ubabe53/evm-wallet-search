#!/usr/bin/env python3
"""Run one bounded dashboard scan into shared raw storage and staged analytics."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from .enrich_token_metadata import JsonRpcCaller, JsonRpcClient
    from .project_config import resolved_runtime
    from .run_dbt import EVM_WALLET_SCAN_ADDRESS_ENV, run_dbt
    from .run_indexer import INDEXER_DIR, bounded_config
    from .snapshot_runs import (
        SCOPE_VERSION,
        ConfiguredWallet,
        FinalizedBlock,
        HyperIndexMetadata,
        dbt_snapshot_environment,
        finish_snapshot_run,
        mark_ingestion_complete,
        start_snapshot_run,
    )
    from .wallet_scan_raw import (
        HASH_PATTERN,
        RawIngestionInterval,
        bounded_indexer_completed,
        completed_ingestion_prefix,
        drop_temporary_schema,
        merge_bounded_ingestion,
    )
except ImportError:
    from enrich_token_metadata import JsonRpcCaller, JsonRpcClient
    from project_config import resolved_runtime
    from run_dbt import EVM_WALLET_SCAN_ADDRESS_ENV, run_dbt
    from run_indexer import INDEXER_DIR, bounded_config
    from snapshot_runs import (
        SCOPE_VERSION,
        ConfiguredWallet,
        FinalizedBlock,
        HyperIndexMetadata,
        dbt_snapshot_environment,
        finish_snapshot_run,
        mark_ingestion_complete,
        start_snapshot_run,
    )
    from wallet_scan_raw import (
        HASH_PATTERN,
        RawIngestionInterval,
        bounded_indexer_completed,
        completed_ingestion_prefix,
        drop_temporary_schema,
        merge_bounded_ingestion,
    )

WRITE_DSN_ENV = "WALLET_SCAN_POSTGRES_DSN"
JOB_ID_PATTERN = re.compile(r"^[0-9a-fA-F-]{8,64}$")


@dataclass(frozen=True)
class WorkerInput:
    job_id: str
    requested_value: str
    wallet_address: str
    wallet_label: str
    from_block: int
    to_block: int
    output_path: Path
    resolver_source: str
    observation_block_hash: str
    observation_timestamp: datetime

    @property
    def schema_name(self) -> str:
        normalized = self.job_id.replace("-", "").lower()
        return f"wallet_scan_{normalized}"


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required by the wallet scan worker")
    return value


def load_worker_input(environment: Mapping[str, str] = os.environ) -> WorkerInput:
    job_id = _required(environment, "WALLET_SCAN_JOB_ID")
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise RuntimeError("WALLET_SCAN_JOB_ID is invalid")
    wallet_address = _required(environment, "WALLET_SCAN_ADDRESS").lower()
    from_block = int(_required(environment, "WALLET_SCAN_FROM_BLOCK"))
    to_block = int(_required(environment, "WALLET_SCAN_TO_BLOCK"))
    observation_number = int(
        _required(environment, "WALLET_SCAN_OBSERVATION_BLOCK_NUMBER")
    )
    observation_hash = _required(
        environment, "WALLET_SCAN_OBSERVATION_BLOCK_HASH"
    ).lower()
    if observation_number != to_block:
        raise RuntimeError("Scan target and finalized observation block do not match")
    interval = RawIngestionInterval(
        wallet_address=wallet_address,
        from_block=from_block,
        to_block=to_block,
        to_block_hash=observation_hash,
    )
    interval.validate()
    observed_at = datetime.fromisoformat(
        _required(environment, "WALLET_SCAN_OBSERVATION_TIMESTAMP").replace("Z", "+00:00")
    )
    if observed_at.tzinfo is None:
        raise RuntimeError("Wallet scan observation timestamp must include a timezone")
    return WorkerInput(
        job_id=job_id,
        requested_value=_required(environment, "WALLET_SCAN_REQUESTED_VALUE"),
        wallet_address=wallet_address,
        wallet_label=_required(environment, "WALLET_SCAN_LABEL"),
        from_block=from_block,
        to_block=to_block,
        output_path=Path(_required(environment, "WALLET_SCAN_OUTPUT_PATH")),
        resolver_source=_required(environment, "WALLET_SCAN_RESOLVER_SOURCE"),
        observation_block_hash=observation_hash,
        observation_timestamp=observed_at,
    )


def postgres_environment(dsn: str) -> dict[str, str]:
    """Translate one explicit write DSN into Envio's external-Postgres contract."""

    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError(f"{WRITE_DSN_ENV} must be a PostgreSQL URI")
    database = parsed.path.lstrip("/")
    if not parsed.hostname or parsed.port is None or not parsed.username or not database:
        raise RuntimeError(f"{WRITE_DSN_ENV} must include host, port, user, and database")
    result = {
        "ENVIO_PG_HOST": parsed.hostname,
        "ENVIO_PG_PORT": str(parsed.port),
        "ENVIO_PG_USER": unquote(parsed.username),
        "ENVIO_PG_PASSWORD": unquote(parsed.password or ""),
        "ENVIO_PG_DATABASE": unquote(database),
    }
    ssl_mode = parse_qs(parsed.query).get("sslmode", [])
    if ssl_mode:
        result["ENVIO_PG_SSL_MODE"] = ssl_mode[-1]
    return result


def configured_start_block(
    database_path: Path,
    *,
    wallet_address: str,
    fallback: int,
) -> int:
    """Read the wallet's cumulative start without consulting fixture configuration."""

    if not database_path.exists():
        return fallback
    import duckdb

    with duckdb.connect(str(database_path), read_only=True) as connection:
        table = connection.execute(
            """
            select count(*) from information_schema.tables
            where table_schema = 'ops' and table_name = 'pipeline_runs'
            """
        ).fetchone()
        if table is None or table[0] == 0:
            return fallback
        row = connection.execute(
            """
            select min(from_block)
            from ops.pipeline_runs
            where chain_id = 1 and wallet_address = ? and scope_version = ?
              and status = 'completed'
            """,
            [wallet_address, SCOPE_VERSION],
        ).fetchone()
    return fallback if row is None or row[0] is None else int(row[0])


def finalized_block_hash(client: JsonRpcCaller, block_number: int) -> str:
    """Re-prove that a requested historical block is within finalized coverage."""

    finalized = client.call("eth_getBlockByNumber", ["finalized", False])
    if not isinstance(finalized, dict) or not finalized.get("number"):
        raise RuntimeError("Ethereum RPC did not return the finalized head")
    finalized_number = int(str(finalized["number"]), 16)
    if finalized_number < block_number:
        raise RuntimeError("Wallet scan target is no longer within finalized coverage")
    block: Any
    if finalized_number == block_number:
        block = finalized
    else:
        block = client.call("eth_getBlockByNumber", [hex(block_number), False])
    if not isinstance(block, dict) or not block.get("number") or not block.get("hash"):
        raise RuntimeError("Ethereum RPC did not return the wallet scan endpoint block")
    returned_number = int(str(block["number"]), 16)
    block_hash = str(block["hash"]).lower()
    if returned_number != block_number or not HASH_PATTERN.fullmatch(block_hash):
        raise RuntimeError("Ethereum RPC returned invalid wallet scan endpoint evidence")
    return block_hash


def _stop_process_group(process: subprocess.Popen[Any]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)


def run_bounded_indexer(
    scan: WorkerInput,
    write_dsn: str,
    *,
    timeout_seconds: int,
    envio_api_token: str | None = None,
) -> None:
    """Supervise Envio until its isolated persisted checkpoint reaches the end."""

    environment = os.environ.copy()
    environment.update(postgres_environment(write_dsn))
    if envio_api_token:
        environment["ENVIO_API_TOKEN"] = envio_api_token
    environment["ENVIO_WALLET_SCAN_ADDRESS"] = scan.wallet_address
    environment["ENVIO_PG_SCHEMA"] = scan.schema_name
    environment["ENVIO_INDEXER_PORT"] = "8082"
    config = bounded_config(
        from_block=scan.from_block,
        to_block=scan.to_block,
        schema_name=scan.schema_name,
    )
    import yaml

    interval = RawIngestionInterval(
        wallet_address=scan.wallet_address,
        from_block=scan.from_block,
        to_block=scan.to_block,
        to_block_hash=scan.observation_block_hash,
    )
    with tempfile.NamedTemporaryFile(
        mode="w",
        prefix="wallet-scan-worker-",
        suffix=".yaml",
        dir=INDEXER_DIR,
    ) as generated:
        yaml.safe_dump(config, generated, sort_keys=False)
        generated.flush()
        process = subprocess.Popen(
            ["bunx", "envio", "start", "--restart", "--config", generated.name],
            cwd=INDEXER_DIR,
            env=environment,
            start_new_session=True,
        )
        deadline = time.monotonic() + timeout_seconds
        try:
            while True:
                if bounded_indexer_completed(
                    write_dsn,
                    schema_name=scan.schema_name,
                    interval=interval,
                ):
                    return
                return_code = process.poll()
                if return_code is not None:
                    raise RuntimeError(
                        "Bounded Envio process exited before completing the requested interval "
                        f"(exit {return_code})"
                    )
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"Bounded Envio scan did not finish within {timeout_seconds} seconds"
                    )
                time.sleep(2)
        finally:
            _stop_process_group(process)


def run_worker(environment: Mapping[str, str] = os.environ) -> None:
    scan = load_worker_input(environment)
    runtime = resolved_runtime()
    write_dsn = environment.get(WRITE_DSN_ENV, "").strip() or str(
        runtime.get("wallet_scan_postgres_dsn") or ""
    )
    rpc_url = environment.get("ETHEREUM_RPC_URL", "").strip() or str(
        runtime.get("ethereum_rpc_url") or ""
    )
    if not write_dsn:
        raise RuntimeError(f"{WRITE_DSN_ENV} is required for bounded scan persistence")
    if not rpc_url:
        raise RuntimeError("ETHEREUM_RPC_URL is required for finalized scan verification")
    timeout_seconds = int(environment.get("WALLET_SCAN_INDEXER_TIMEOUT_SECONDS", "7200"))
    if not 1 <= timeout_seconds <= 86400:
        raise RuntimeError("WALLET_SCAN_INDEXER_TIMEOUT_SECONDS must be between 1 and 86400")

    coverage_start = configured_start_block(
        scan.output_path,
        wallet_address=scan.wallet_address,
        fallback=scan.from_block,
    )
    from server.ens import ResolvedScanInput

    scan_input = ResolvedScanInput(
        original_input=scan.requested_value,
        normalized_name=(
            scan.wallet_label.lower() if scan.wallet_label.lower().endswith(".eth") else None
        ),
        resolved_address=scan.wallet_address,
        resolver_source=scan.resolver_source,
        observation_block_number=scan.to_block,
        observation_block_hash=scan.observation_block_hash,
        observed_at=scan.observation_timestamp,
    )
    run = start_snapshot_run(
        database_path=scan.output_path,
        wallet=ConfiguredWallet(scan.wallet_address, scan.wallet_label),
        metadata=HyperIndexMetadata(
            start_block=coverage_start,
            progress_block=scan.to_block,
            end_block=scan.to_block,
            is_ready=True,
        ),
        finalized_block=FinalizedBlock(scan.to_block, scan.observation_block_hash),
        scan_input=scan_input,
    )
    if run.from_block != scan.from_block or run.to_block != scan.to_block:
        finish_snapshot_run(run, database_path=scan.output_path, succeeded=False)
        raise RuntimeError("Staged artifact coverage does not match the requested missing interval")

    interval = RawIngestionInterval(
        wallet_address=scan.wallet_address,
        from_block=scan.from_block,
        to_block=scan.to_block,
        to_block_hash=scan.observation_block_hash,
    )
    rpc_client = JsonRpcClient(rpc_url)
    try:
        verified_endpoint_hash = finalized_block_hash(rpc_client, scan.to_block)
        if verified_endpoint_hash != scan.observation_block_hash:
            raise RuntimeError(
                "Wallet scan endpoint hash changed since the finalized observation"
            )
        next_raw_block, raw_events_found = completed_ingestion_prefix(write_dsn, interval)
        if next_raw_block <= scan.to_block:
            pending_scan = replace(scan, from_block=next_raw_block)
            pending_interval = replace(interval, from_block=next_raw_block)
            try:
                run_bounded_indexer(
                    pending_scan,
                    write_dsn,
                    timeout_seconds=timeout_seconds,
                    envio_api_token=str(runtime.get("envio_api_token") or "") or None,
                )
                raw_events_found += merge_bounded_ingestion(
                    write_dsn,
                    schema_name=scan.schema_name,
                    interval=pending_interval,
                    finalized_hash_resolver=lambda block: (
                        verified_endpoint_hash
                        if block == scan.to_block
                        else finalized_block_hash(rpc_client, block)
                    ),
                )
            finally:
                drop_temporary_schema(write_dsn, scan.schema_name)
        mark_ingestion_complete(
            run,
            raw_events_found=raw_events_found,
            database_path=scan.output_path,
        )
        run_dbt(
            "build",
            ["--vars", '{"use_fixture": false}'],
            use_hyperindex=True,
            # Reuse the exact persistence target; run_dbt attaches it read-only.
            hyperindex_dsn=write_dsn,
            extra_env=dbt_snapshot_environment(run)
            | {EVM_WALLET_SCAN_ADDRESS_ENV: scan.wallet_address},
            database_path_override=scan.output_path,
        )
        finish_snapshot_run(run, database_path=scan.output_path, succeeded=True)
    except BaseException:
        finish_snapshot_run(run, database_path=scan.output_path, succeeded=False)
        raise


def main() -> None:
    run_worker()


if __name__ == "__main__":
    main()
