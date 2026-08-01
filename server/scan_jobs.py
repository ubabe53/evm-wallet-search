"""Single-worker wallet scan orchestration and its stable adapter boundary.

The current repository still has a single-wallet HyperIndex schema.  This module
owns the application contract needed by the multi-wallet/indexer branch without
claiming that the existing indexer can scan arbitrary wallets yet.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
import threading
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

from scripts.artifact_paths import LIVE_DB_PATH
from server.ens import ResolvedScanInput, resolve_scan_input

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
    """Run the future indexer adapter using an explicit command contract.

    The command must write a complete DuckDB artifact to WALLET_SCAN_OUTPUT_PATH.
    It receives WALLET_SCAN_FROM_BLOCK=0 and the finalized target selected by the
    API.  No command means the installation is not yet wired to multi-wallet
    HyperIndex; importantly, no failed or partial artifact is served.
    """
    command_text = os.environ.get("WALLET_SCAN_COMMAND")
    if not command_text:
        raise RuntimeError(
            "Wallet scan worker is not configured; set WALLET_SCAN_COMMAND from the multi-wallet indexer branch"
        )
    environment = os.environ.copy()
    environment.update({
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
    subprocess.run(shlex.split(command_text), check=True, env=environment)
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
        url = os.environ.get("ETHEREUM_RPC_URL") or os.environ.get("PUBLIC_RPC_URL")
        if not url:
            raise RuntimeError("ETHEREUM_RPC_URL is required to resolve the finalized head")
        request = __import__("urllib.request", fromlist=["Request"]).Request(
            url,
            data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBlockByNumber", "params": ["finalized", False]}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with __import__("urllib.request", fromlist=["urlopen"]).urlopen(request, timeout=45) as response:
            payload = json.load(response)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or not isinstance(result.get("number"), str):
            raise RuntimeError("Ethereum finalized head could not be resolved")
        return int(result["number"], 16)

    def _rpc_client(self):
        manager = self

        class RpcClient:
            def call(self, method: str, params: list[object]) -> object:
                url = os.environ.get("ETHEREUM_RPC_URL") or os.environ.get("PUBLIC_RPC_URL")
                if not url:
                    raise RuntimeError("ETHEREUM_RPC_URL is required to resolve the finalized head")
                request = __import__("urllib.request", fromlist=["Request"]).Request(
                    url,
                    data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with __import__("urllib.request", fromlist=["urlopen"]).urlopen(request, timeout=45) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict) or "error" in payload:
                    raise RuntimeError("Ethereum RPC request failed")
                return payload.get("result")

        del manager
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
        now = utc_now()
        job = ScanJob(
            str(uuid.uuid4()), requested_value.strip(), address, label, "queued", 0, 0, target, None, now, now,
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
        current = self._current_wallet()
        if current:
            address = current.get("wallet_address")
            if isinstance(address, str):
                wallets[address] = current
        return sorted(wallets.values(), key=lambda row: str(row["wallet_address"]))

    def _current_wallet(self) -> dict[str, object] | None:
        if not self.live_path.is_file():
            return None
        try:
            import duckdb
            with duckdb.connect(str(self.live_path), read_only=True) as connection:
                row = connection.execute("select chain_id, wallet_address, configured_wallet_label from pipeline_metadata limit 1").fetchone()
            if row is None:
                return None
            return {"chain_id": row[0], "wallet_address": row[1], "label": row[2], "status": "completed"}
        except Exception:
            return None

    def _run(self, original: ScanJob) -> None:
        with self._lock:
            self._jobs[original.job_id] = replace(original, status="running", progress=1, updated_at=utc_now())
        try:
            self.live_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="wallet-scan-", dir=str(self.live_path.parent)) as directory:
                staging = Path(directory) / "live.duckdb"
                self.worker(original, staging, lambda value: self._progress(original.job_id, value))
                self._preserve_token_overrides(staging)
                self._validate_staged_artifact(original, staging)
                os.replace(staging, self.live_path)
            self._finish(original.job_id, "completed", 100, None)
        except Exception as error:
            self._finish(original.job_id, "failed", 0, str(error))
        finally:
            with self._lock:
                self._active_job_id = None

    def _preserve_token_overrides(self, staging_path: Path) -> None:
        """Carry application-owned token overrides across an artifact swap."""

        if not self.live_path.is_file():
            return
        try:
            import duckdb

            with duckdb.connect(str(staging_path)) as connection:
                live_path = str(self.live_path).replace("'", "''")
                connection.execute(f"attach '{live_path}' as previous_live (read_only)")
                try:
                    exists = connection.execute(
                        """
                        select count(*)
                        from duckdb_tables()
                        where database_name = 'previous_live'
                          and schema_name = 'app' and table_name = 'token_recognition_overrides'
                        """
                    ).fetchone()[0]
                    if not exists:
                        return
                    connection.execute("create schema if not exists app")
                    connection.execute("drop table if exists app.token_recognition_overrides")
                    connection.execute(
                        """
                        create table app.token_recognition_overrides (
                          chain_id integer not null check (chain_id = 1),
                          token_address varchar not null,
                          status varchar not null check (status in ('recognized', 'other')),
                          updated_at timestamptz not null default current_timestamp,
                          primary key (chain_id, token_address)
                        )
                        """
                    )
                    connection.execute(
                        """
                        insert into app.token_recognition_overrides
                        select chain_id, token_address, status, updated_at
                        from previous_live.app.token_recognition_overrides
                        """
                    )
                finally:
                    connection.execute("detach previous_live")
        except Exception as error:
            raise RuntimeError("Could not preserve token-recognition overrides") from error

    @staticmethod
    def _validate_staged_artifact(job: ScanJob, staging_path: Path) -> None:
        if not staging_path.is_file():
            raise RuntimeError("Wallet scan worker completed without producing an artifact")
        try:
            import duckdb
            with duckdb.connect(str(staging_path), read_only=True) as connection:
                for relation in ("pipeline_metadata", "wallet_events", "token_summary", "counterparty_summary", "timeline_daily"):
                    connection.execute(f"select count(*) from {relation}")
                row = connection.execute(
                    """
                    select wallet_address, data_source, snapshot_start_block,
                           snapshot_end_block, snapshot_end_block_hash,
                           snapshot_finality_policy
                    from pipeline_metadata
                    """
                ).fetchone()
        except Exception as error:
            raise RuntimeError("Wallet scan worker produced an unreadable analytics artifact") from error
        if row is None or row[0] != job.wallet_address or row[1] != "hyperindex":
            raise RuntimeError("Wallet scan artifact has incorrect wallet or live provenance")
        if row[2] != job.from_block or row[3] != job.to_block or not row[4]:
            raise RuntimeError("Wallet scan artifact does not cover the requested block range")
        if job.observation_block_hash and row[4].lower() != job.observation_block_hash.lower():
            raise RuntimeError("Wallet scan artifact finalized block hash does not match the scan observation")
        if row[5] != "ethereum_finalized":
            raise RuntimeError("Wallet scan artifact is not finalized")

    def _progress(self, job_id: str, value: int) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = replace(job, progress=max(0, min(99, value)), updated_at=utc_now())

    def _finish(self, job_id: str, status: str, progress: int, error: str | None) -> None:
        with self._lock:
            job = self._jobs[job_id]
            self._jobs[job_id] = replace(job, status=status, progress=progress, error=error, updated_at=utc_now())
