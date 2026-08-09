"""Single-worker bounded wallet scans with validated atomic publication."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from scripts.artifact_paths import LIVE_DB_PATH
from scripts.project_config import resolved_runtime
from server.ens import ResolvedScanInput, resolve_scan_input

RPC_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "evm-wallet-search/0.1",
}

ADDRESS_PATTERN = r"^0x[0-9a-fA-F]{40}$"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ScanJob:
    job_id: str
    requested_value: str
    wallet_address: str
    wallet_label: str
    status: str
    progress: int
    from_block: int
    to_block: int
    error: str | None
    created_at: str
    updated_at: str
    resolver_source: str | None = None
    observation_block_number: int | None = None
    observation_block_hash: str | None = None
    observation_timestamp: str | None = None


class ScanWorker(Protocol):
    def __call__(self, job: ScanJob, staging_path: Path, progress: Callable[[int], None]) -> None: ...


class WalletResolver(Protocol):
    def __call__(self, value: str) -> tuple[str, str]: ...


class ScanInputResolver(Protocol):
    def __call__(self, value: str) -> ResolvedScanInput: ...


def resolve_wallet(value: str) -> tuple[str, str]:
    """Resolve canonical addresses and the configured ENS adapter.

    ENS is intentionally an adapter: live ENS resolution belongs to the future
    multi-wallet branch and must add resolver source and observation metadata.
    """
    normalized = value.strip()
    import re

    if re.fullmatch(ADDRESS_PATTERN, normalized):
        address = normalized.lower()
        return address, address
    if normalized.lower() == "vitalik.eth":
        return "0xd8da6bf26964af9d7eed9e03e53415d37aa96045", normalized.lower()
    if normalized.lower().endswith(".eth"):
        raise ValueError("ENS resolution is not configured for this name yet")
    raise ValueError("Enter a valid Ethereum address or ENS name")


def configured_scan_worker(job: ScanJob, staging_path: Path, progress: Callable[[int], None]) -> None:
    """Run the bundled worker or an explicitly overridden adapter command.

    The worker must update the complete DuckDB artifact already present at
    WALLET_SCAN_OUTPUT_PATH. It receives the wallet-specific missing range and
    finalized target selected by the API. WALLET_SCAN_COMMAND can override the
    bundled implementation without changing the publication boundary.
    """
    command_text = os.environ.get("WALLET_SCAN_COMMAND", "").strip()
    command = (
        shlex.split(command_text)
        if command_text
        else [sys.executable, str(Path(__file__).parents[1] / "scripts" / "wallet_scan_worker.py")]
    )
    environment = os.environ.copy()
    environment.update({
        "WALLET_SCAN_JOB_ID": job.job_id,
        "WALLET_SCAN_REQUESTED_VALUE": job.requested_value,
        "WALLET_SCAN_ADDRESS": job.wallet_address,
        "WALLET_SCAN_LABEL": job.wallet_label,
        "WALLET_SCAN_FROM_BLOCK": str(job.from_block),
        "WALLET_SCAN_TO_BLOCK": str(job.to_block),
        "WALLET_SCAN_OUTPUT_PATH": str(staging_path),
    })
    if job.resolver_source:
        environment["WALLET_SCAN_RESOLVER_SOURCE"] = job.resolver_source
    if job.observation_block_number is not None:
        environment["WALLET_SCAN_OBSERVATION_BLOCK_NUMBER"] = str(job.observation_block_number)
    if job.observation_block_hash:
        environment["WALLET_SCAN_OBSERVATION_BLOCK_HASH"] = job.observation_block_hash
    if job.observation_timestamp:
        environment["WALLET_SCAN_OBSERVATION_TIMESTAMP"] = job.observation_timestamp
    progress(5)
    subprocess.run(command, check=True, env=environment)
    if not staging_path.is_file():
        raise RuntimeError("Wallet scan worker completed without producing an artifact")
    progress(95)


class ScanJobManager:
    def __init__(
        self,
        live_path: Path = LIVE_DB_PATH,
        *,
        resolver: WalletResolver | None = None,
        scan_input_resolver: ScanInputResolver | None = None,
        worker: ScanWorker = configured_scan_worker,
        finalized_head: Callable[[], int] | None = None,
    ) -> None:
        self.live_path = live_path
        self.resolver = resolver
        self.scan_input_resolver = scan_input_resolver or self._resolve_scan_input
        self.worker = worker
        self.finalized_head = finalized_head or self._rpc_finalized_head
        self._jobs: dict[str, ScanJob] = {}
        self._lock = threading.Lock()
        self._active_job_id: str | None = None

    def _rpc_finalized_head(self) -> int:
        url = self._rpc_url()
        request = __import__("urllib.request", fromlist=["Request"]).Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber", "params": ["finalized", False]}).encode(),
            headers=RPC_HEADERS,
        )
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(request, timeout=45) as response:
            payload = json.load(response)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or not isinstance(result.get("number"), str):
            raise RuntimeError("Ethereum finalized head could not be resolved")
        return int(result["number"], 16)

    @staticmethod
    def _rpc_url() -> str:
        url = resolved_runtime().get("ethereum_rpc_url")
        if not url:
            raise RuntimeError("ETHEREUM_RPC_URL is required to resolve the finalized head")
        return str(url)

    def _rpc_client(self):
        manager = self

        class RpcClient:
            def call(self, method: str, params: list[object]) -> object:
                url = manager._rpc_url()
                request = __import__("urllib.request", fromlist=["Request"]).Request(
                    url,
                    data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                    headers=RPC_HEADERS,
                )
                with __import__("urllib.request", fromlist=["urlopen"]).urlopen(request, timeout=45) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict) or "error" in payload:
                    raise RuntimeError("Ethereum RPC request failed")
                return payload.get("result")

        return RpcClient()

    def _resolve_scan_input(self, value: str) -> ResolvedScanInput:
        return resolve_scan_input(value, self._rpc_client())

    def create(self, requested_value: str) -> ScanJob:
        try:
            if self.resolver is not None:
                address, label = self.resolver(requested_value)
                target = self.finalized_head()
                resolved = None
            else:
                resolved = self.scan_input_resolver(requested_value)
                address = resolved.resolved_address
                label = resolved.normalized_name or address
                target = resolved.observation_block_number
        except ValueError:
            raise
        except Exception as error:
            raise RuntimeError(str(error)) from error
        if target < 0:
            raise RuntimeError("Finalized head must be non-negative")
        from_block = self._next_from_block(address)
        if from_block > target:
            raise RuntimeError(
                f"Wallet {address} is already scanned through finalized block {target}"
            )
        now = utc_now()
        job = ScanJob(
            str(uuid.uuid4()), requested_value.strip(), address, label, "queued", 0, from_block, target, None, now, now,
            resolved.resolver_source if resolved else None,
            resolved.observation_block_number if resolved else None,
            resolved.observation_block_hash if resolved else None,
            resolved.observed_at.isoformat() if resolved else None,
        )
        with self._lock:
            if self._active_job_id is not None:
                raise RuntimeError("A wallet scan is already running; wait for it to finish")
            self._jobs[job.job_id] = job
            self._active_job_id = job.job_id
        threading.Thread(target=self._run, args=(job,), daemon=True).start()
        return job

    def get(self, job_id: str) -> ScanJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_wallets(self) -> list[dict[str, object]]:
        wallets: dict[str, dict[str, object]] = {}
        with self._lock:
            jobs = tuple(self._jobs.values())
        for job in jobs:
            if job.status == "completed":
                wallets[job.wallet_address] = {"chain_id": 1, "wallet_address": job.wallet_address, "label": job.wallet_label, "status": "completed"}
        for current in self._current_wallets():
            address = current.get("wallet_address")
            if isinstance(address, str):
                wallets[address] = current
        return sorted(wallets.values(), key=lambda row: str(row["wallet_address"]))

    def _current_wallets(self) -> list[dict[str, object]]:
        if not self.live_path.is_file():
            return []
        try:
            import duckdb
            with duckdb.connect(str(self.live_path), read_only=True) as connection:
                rows = connection.execute(
                    "select chain_id, wallet_address, configured_wallet_label from pipeline_metadata order by chain_id, wallet_address"
                ).fetchall()
            return [
                {"chain_id": row[0], "wallet_address": row[1], "label": row[2], "status": "completed"}
                for row in rows
            ]
        except Exception:
            return []

    def _next_from_block(self, wallet_address: str) -> int:
        """Return the first missing block for one wallet in the complete artifact."""

        if not self.live_path.is_file():
            return 0
        try:
            import duckdb

            with duckdb.connect(str(self.live_path), read_only=True) as connection:
                row = connection.execute(
                    """
                    select max(snapshot_end_block)
                    from pipeline_metadata
                    where chain_id = 1 and lower(wallet_address) = lower(?)
                    """,
                    [wallet_address],
                ).fetchone()
            return 0 if row is None or row[0] is None else int(row[0]) + 1
        except Exception:
            # A new artifact has no metadata yet. Validation will still reject
            # malformed worker output before it can replace the served artifact.
            return 0

    def _run(self, original: ScanJob) -> None:
        with self._lock:
            self._jobs[original.job_id] = replace(original, status="running", progress=1, updated_at=utc_now())
        try:
            self.live_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="wallet-scan-", dir=str(self.live_path.parent)) as directory:
                staging = Path(directory) / "live.duckdb"
                if self.live_path.is_file():
                    shutil.copy2(self.live_path, staging)
                self.worker(original, staging, lambda value: self._progress(original.job_id, value))
                self._validate_staged_artifact(original, staging, self.live_path if self.live_path.is_file() else None)
                os.replace(staging, self.live_path)
            self._finish(original.job_id, "completed", 100, None)
        except Exception as error:
            self._finish(original.job_id, "failed", 0, str(error))
        finally:
            with self._lock:
                self._active_job_id = None

    @staticmethod
    def _validate_staged_artifact(job: ScanJob, staging_path: Path, previous_path: Path | None) -> None:
        if not staging_path.is_file():
            raise RuntimeError("Wallet scan worker completed without producing an artifact")
        try:
            import duckdb
            with duckdb.connect(str(staging_path), read_only=True) as connection:
                for relation in ("pipeline_metadata", "wallet_events", "token_summary", "counterparty_summary", "timeline_daily"):
                    connection.execute(f"select count(*) from {relation}")
                rows = connection.execute(
                    """
                    select wallet_address, data_source, snapshot_start_block,
                           snapshot_end_block, snapshot_end_block_hash,
                           snapshot_finality_policy
                    from pipeline_metadata
                    order by wallet_address
                    """
                ).fetchall()
        except Exception as error:
            raise RuntimeError("Wallet scan worker produced an unreadable analytics artifact") from error
        row = next((item for item in rows if item[0] == job.wallet_address), None)
        if row is None or row[1] != "hyperindex":
            raise RuntimeError("Wallet scan artifact has incorrect wallet or live provenance")
        expected_snapshot_start = job.from_block
        if previous_path is not None:
            try:
                import duckdb

                with duckdb.connect(str(staging_path), read_only=True) as connection:
                    previous = str(previous_path).replace("'", "''")
                    connection.execute(f"attach '{previous}' as previous_live (read_only)")
                    previous_metadata_count = connection.execute(
                        """
                        select count(*)
                        from duckdb_tables()
                        where database_name = 'previous_live'
                          and schema_name = 'main' and table_name = 'pipeline_metadata'
                        """
                    ).fetchone()
                    previous_metadata_exists = bool(
                        previous_metadata_count is not None and previous_metadata_count[0]
                    )
                    previous_row = (
                        connection.execute(
                            """
                            select snapshot_start_block
                            from previous_live.main.pipeline_metadata
                            where lower(wallet_address) = lower(?)
                            """,
                            [job.wallet_address],
                        ).fetchone()
                        if previous_metadata_exists
                        else None
                    )
                if previous_row is not None and previous_row[0] is not None:
                    expected_snapshot_start = int(previous_row[0])
            except Exception as error:
                raise RuntimeError("Wallet scan artifact could not verify prior wallet coverage") from error
        # snapshot_start_block is the wallet's cumulative coverage start, so an
        # extending scan may legitimately begin after this value. The staged
        # artifact must preserve that start and end at the requested finalized block.
        if row[2] != expected_snapshot_start or row[3] != job.to_block or not row[4]:
            raise RuntimeError("Wallet scan artifact does not cover the requested block range")
        if job.observation_block_hash and row[4].lower() != job.observation_block_hash.lower():
            raise RuntimeError("Wallet scan artifact finalized block hash does not match the scan observation")
        if row[5] != "ethereum_finalized":
            raise RuntimeError("Wallet scan artifact is not finalized")
        if previous_path is not None:
            try:
                import duckdb

                with duckdb.connect(str(staging_path), read_only=True) as connection:
                    previous = str(previous_path).replace("'", "''")
                    connection.execute(f"attach '{previous}' as previous_live (read_only)")
                    try:
                        def count_rows(query: str, parameters: list[object] | None = None) -> int:
                            result = connection.execute(query, parameters or [])
                            row = result.fetchone()
                            if row is None:
                                raise RuntimeError("DuckDB count query returned no row")
                            return int(row[0])

                        previous_tables = {
                            (item[0], item[1])
                            for item in connection.execute(
                                """
                                select schema_name, table_name from duckdb_tables()
                                where database_name = 'previous_live'
                                """
                            ).fetchall()
                        }
                        staged_tables = {
                            (item[0], item[1])
                            for item in connection.execute(
                                """
                                select schema_name, table_name from duckdb_tables()
                                where database_name = current_database()
                                """
                            ).fetchall()
                        }
                        previous_metadata_exists = (
                            "main", "pipeline_metadata"
                        ) in previous_tables
                        previous_wallets = (
                            {
                                item[0]
                                for item in connection.execute(
                                    "select wallet_address from previous_live.main.pipeline_metadata"
                                ).fetchall()
                            }
                            if previous_metadata_exists
                            else set()
                        )
                        staged_wallets = {item[0] for item in rows}
                        if not previous_wallets.issubset(staged_wallets):
                            raise RuntimeError("Wallet scan artifact dropped an existing wallet")

                        for relation in (
                            "wallet_events",
                            "token_summary",
                            "counterparty_summary",
                            "timeline_daily",
                            "int_wallet_transfer_events",
                            "token_rpc_metadata",
                            "int_token_enrichment",
                        ):
                            if ("main", relation) not in previous_tables:
                                continue
                            if ("main", relation) not in staged_tables:
                                raise RuntimeError(f"Wallet scan artifact dropped relation {relation}")
                        wallet_event_columns = {
                            item[0]
                            for item in connection.execute(
                                """
                                select column_name from duckdb_columns()
                                where database_name = 'previous_live'
                                  and schema_name = 'main' and table_name = 'wallet_events'
                                """
                            ).fetchall()
                        }
                        wallet_event_identity = {
                            "chain_id", "wallet_address", "transaction_hash", "log_index"
                        }
                        if not wallet_event_columns:
                            missing_events = 0
                        elif wallet_event_identity.issubset(wallet_event_columns):
                            missing_events = count_rows(
                                """
                                select count(*) from (
                                  select chain_id, lower(wallet_address) as wallet_address,
                                         lower(transaction_hash) as transaction_hash, log_index
                                  from previous_live.main.wallet_events
                                  except all
                                  select chain_id, lower(wallet_address) as wallet_address,
                                         lower(transaction_hash) as transaction_hash, log_index
                                  from main.wallet_events
                                )
                                """
                            )
                        else:
                            # Compatibility path for an older or adapter-owned artifact:
                            # without the canonical key, require exact row preservation.
                            missing_events = count_rows(
                                """
                                select count(*) from (
                                  select * from previous_live.main.wallet_events
                                  except all
                                  select * from main.wallet_events
                                )
                                """
                            )
                        if missing_events:
                            raise RuntimeError("Wallet scan artifact dropped rows from wallet_events")

                        immutable_event_columns = (
                            "chain_id", "block_number", "block_hash", "block_timestamp",
                            "transaction_hash", "transaction_index", "transaction_from_address",
                            "transaction_to_address", "log_index", "wallet_address",
                            "token_address", "from_address", "to_address",
                            "transaction_sender_relation", "transaction_target_relation",
                            "is_indirect", "direction", "counterparty_address", "value_raw",
                        )
                        intermediate_columns = {
                            item[0]
                            for item in connection.execute(
                                """
                                select column_name from duckdb_columns()
                                where database_name = 'previous_live'
                                  and schema_name = 'main'
                                  and table_name = 'int_wallet_transfer_events'
                                """
                            ).fetchall()
                        }
                        if set(immutable_event_columns).issubset(intermediate_columns):
                            projection = ", ".join(immutable_event_columns)
                            missing_facts = count_rows(
                                f"""
                                select count(*) from (
                                  select {projection}
                                  from previous_live.main.int_wallet_transfer_events
                                  except all
                                  select {projection}
                                  from main.int_wallet_transfer_events
                                )
                                """
                            )
                            if missing_facts:
                                raise RuntimeError(
                                    "Wallet scan artifact changed or dropped immutable event facts"
                                )

                        for relation in ("token_rpc_metadata",):
                            if ("main", relation) not in previous_tables:
                                continue
                            missing = count_rows(
                                f"select count(*) from (select * from previous_live.main.\"{relation}\" except all select * from main.\"{relation}\")"
                            )
                            if missing:
                                raise RuntimeError(f"Wallet scan artifact dropped rows from {relation}")

                        for relation in (
                            "wallet_targets",
                            "scan_generations",
                            "pipeline_runs",
                        ):
                            if ("ops", relation) not in previous_tables:
                                continue
                            if ("ops", relation) not in staged_tables:
                                raise RuntimeError(f"Wallet scan artifact dropped relation ops.{relation}")
                            missing = count_rows(
                                f"select count(*) from (select * from previous_live.ops.\"{relation}\" except all select * from ops.\"{relation}\")",
                            )
                            if missing:
                                raise RuntimeError(f"Wallet scan artifact dropped rows from ops.{relation}")

                        if previous_metadata_exists:
                            metadata_missing = count_rows(
                                """
                                select count(*) from (
                                  select * from previous_live.main.pipeline_metadata
                                  where wallet_address <> ?
                                  except all
                                  select * from main.pipeline_metadata
                                  where wallet_address <> ?
                                )
                                """,
                                [job.wallet_address, job.wallet_address])
                            if metadata_missing:
                                raise RuntimeError("Wallet scan artifact changed existing wallet metadata")

                        for schema_name, relation in connection.execute(
                            """
                            select schema_name, table_name
                            from duckdb_tables()
                            where database_name = 'previous_live'
                              and schema_name in ('main', 'app')
                            order by schema_name, table_name
                            """
                        ).fetchall():
                            if schema_name == "main" and relation == "pipeline_metadata":
                                continue
                            if (schema_name, relation) not in staged_tables:
                                raise RuntimeError(f"Wallet scan artifact dropped relation {schema_name}.{relation}")
                            if schema_name == "app":
                                missing = count_rows(
                                    f"select count(*) from (select * from previous_live.\"{schema_name}\".\"{relation}\" except all select * from \"{schema_name}\".\"{relation}\")"
                                )
                                if missing:
                                    raise RuntimeError(
                                        f"Wallet scan artifact dropped rows from {schema_name}.{relation}"
                                    )

                        if ("app", "token_recognition_overrides") in previous_tables:
                            if ("app", "token_recognition_overrides") not in staged_tables:
                                raise RuntimeError("Wallet scan artifact dropped token-recognition overrides")
                            override_missing = count_rows(
                                """
                                select count(*) from (
                                  select * from previous_live.app.token_recognition_overrides
                                  except all
                                  select * from app.token_recognition_overrides
                                )
                                """
                            )
                            if override_missing:
                                raise RuntimeError("Wallet scan artifact dropped token-recognition overrides")
                    finally:
                        connection.execute("detach previous_live")
            except Exception as error:
                if isinstance(error, RuntimeError):
                    raise
                raise RuntimeError(f"Could not compare staged and existing wallet data: {error}") from error

    def _progress(self, job_id: str, value: int) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = replace(job, progress=max(0, min(99, value)), updated_at=utc_now())

    def _finish(self, job_id: str, status: str, progress: int, error: str | None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = replace(job, status=status, progress=progress, error=error, updated_at=utc_now())
