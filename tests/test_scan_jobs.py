import shutil
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from unittest.mock import patch

import duckdb

from server.ens import ResolvedScanInput
from server.scan_jobs import (
    ScanJob,
    ScanJobManager,
    configured_scan_worker,
    resolve_wallet,
)


class ScanJobsTest(unittest.TestCase):
    @patch(
        "server.scan_jobs.resolved_runtime",
        return_value={"ethereum_rpc_url": "https://configured-rpc.example"},
    )
    def test_scan_resolution_uses_shared_runtime_rpc_configuration(self, _runtime) -> None:
        self.assertEqual(
            ScanJobManager._rpc_url(),
            "https://configured-rpc.example",
        )

    @patch(
        "server.scan_jobs.resolved_runtime",
        return_value={"ethereum_rpc_url": "https://configured-rpc.example"},
    )
    @patch("server.scan_jobs.json.load")
    @patch("urllib.request.urlopen")
    def test_scan_rpc_requests_use_project_user_agent(self, urlopen, load, _runtime) -> None:
        load.return_value = {"result": {"number": "0x64"}}
        manager = ScanJobManager()

        self.assertEqual(manager._rpc_finalized_head(), 100)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "evm-wallet-search/0.1")

        load.return_value = {"result": "0x1"}
        self.assertEqual(manager._rpc_client().call("eth_chainId", []), "0x1")
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "evm-wallet-search/0.1")

    @patch("server.scan_jobs.subprocess.run")
    def test_bundled_worker_receives_job_identity_and_original_input(self, run) -> None:
        with tempfile.TemporaryDirectory() as directory:
            staging = Path(directory) / "live.duckdb"
            staging.touch()
            job = ScanJob(
                job_id="12345678-abcd-1234-abcd-1234567890ab",
                requested_value="alice.eth",
                wallet_address="0x" + "a" * 40,
                wallet_label="alice.eth",
                status="running",
                progress=1,
                from_block=10,
                to_block=20,
                error=None,
                created_at="2026-08-06T12:00:00+00:00",
                updated_at="2026-08-06T12:00:00+00:00",
                resolver_source="ens-registry:test/resolver:test",
                observation_block_number=20,
                observation_block_hash="0x" + "b" * 64,
                observation_timestamp="2026-08-06T12:00:00+00:00",
            )
            progress = []
            with patch.dict("server.scan_jobs.os.environ", {}, clear=True):
                configured_scan_worker(job, staging, progress.append)

        command = run.call_args.args[0]
        environment = run.call_args.kwargs["env"]
        self.assertTrue(str(command[-1]).endswith("scripts/wallet_scan_worker.py"))
        self.assertEqual(environment["WALLET_SCAN_JOB_ID"], job.job_id)
        self.assertEqual(environment["WALLET_SCAN_REQUESTED_VALUE"], "alice.eth")
        self.assertEqual(progress, [5, 95])

    def test_serializes_jobs_and_replaces_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            with duckdb.connect(str(live)) as connection:
                connection.execute("create table marker (value varchar)")
                connection.execute("insert into marker values ('old')")
                connection.execute("create schema app")
                connection.execute(
                    """
                    create table app.token_recognition_overrides (
                      chain_id integer, token_address varchar, status varchar, updated_at timestamptz
                    )
                    """
                )
                connection.execute(
                    "insert into app.token_recognition_overrides values (1, ?, 'recognized', current_timestamp)",
                    ["0x" + "2" * 40],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                progress(40)
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute("insert into marker values (?)", [job.wallet_address])
                    connection.execute("create table if not exists wallet_events (wallet_address varchar)")
                    connection.execute("create table if not exists token_summary (wallet_address varchar)")
                    connection.execute("create table if not exists counterparty_summary (wallet_address varchar)")
                    connection.execute("create table if not exists timeline_daily (wallet_address varchar)")
                    connection.execute(
                        "create table if not exists pipeline_metadata (wallet_address varchar, data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint, snapshot_end_block_hash varchar, snapshot_finality_policy varchar, generated_at timestamptz)"
                    )
                    connection.execute(
                        "insert into pipeline_metadata values (?, 'hyperindex', 0, 123, '0xhash', 'ethereum_finalized', current_timestamp)",
                        [job.wallet_address],
                    )
                progress(90)

            manager = ScanJobManager(live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 123)
            first = manager.create("0x" + "1" * 40)
            with self.assertRaisesRegex(RuntimeError, "already running"):
                manager.create("0x" + "2" * 40)
            for _ in range(50):
                current = manager.get(first.job_id)
                if current and current.status == "completed":
                    break
                time.sleep(0.01)
            completed = manager.get(first.job_id)
            assert completed is not None
            self.assertEqual(completed.status, "completed", completed.error)
            with duckdb.connect(str(live), read_only=True) as connection:
                marker_values = {
                    row[0] for row in connection.execute("select value from marker").fetchall()
                }
                self.assertEqual(marker_values, {"old", "0x" + "1" * 40})
                override = connection.execute(
                    "select chain_id, token_address, status from app.token_recognition_overrides"
                ).fetchone()
                self.assertEqual(override, (1, "0x" + "2" * 40, "recognized"))
            self.assertEqual(completed.from_block, 0)
            self.assertEqual(completed.to_block, 123)

    def test_scan_adds_wallet_without_dropping_existing_wallet_or_shared_override(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            wallet_a = "0x" + "a" * 40
            wallet_b = "0x" + "b" * 40
            token = "0x" + "2" * 40
            with duckdb.connect(str(live)) as connection:
                for relation in ("wallet_events", "token_summary", "counterparty_summary", "timeline_daily"):
                    connection.execute(f"create table {relation} (wallet_address varchar)")
                connection.execute(
                    """
                    create table pipeline_metadata (
                      chain_id integer, wallet_address varchar, configured_wallet_label varchar,
                      data_source varchar, generated_at timestamptz,
                      snapshot_start_block bigint, snapshot_end_block bigint,
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', timestamptz '2026-08-09 00:00:00+00', 0, 10, ?, 'ethereum_finalized')",
                    [wallet_a, "0x" + "a" * 64],
                )
                connection.execute("create schema app")
                connection.execute(
                    "create table app.token_recognition_overrides (chain_id integer, token_address varchar, status varchar, updated_at timestamptz)"
                )
                connection.execute(
                    "insert into app.token_recognition_overrides values (1, ?, 'recognized', current_timestamp)",
                    [token],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                self.assertEqual(job.wallet_address, wallet_b)
                self.assertEqual(job.from_block, 0)
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute(
                        "update pipeline_metadata set generated_at = timestamptz '2026-08-10 00:00:00+00' where wallet_address = ?",
                        [wallet_a],
                    )
                    connection.execute(
                        "insert into pipeline_metadata values (1, ?, 'wallet-b', 'hyperindex', timestamptz '2026-08-10 00:00:00+00', ?, ?, ?, 'ethereum_finalized')",
                        [wallet_b, job.from_block, job.to_block, "0x" + "b" * 64],
                    )
                progress(90)

            manager = ScanJobManager(
                live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 20
            )
            job = manager.create(wallet_b)
            for _ in range(50):
                current = manager.get(job.job_id)
                if current and current.status in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            completed = manager.get(job.job_id)
            assert completed is not None
            self.assertEqual(completed.status, "completed", completed.error)
            with duckdb.connect(str(live), read_only=True) as connection:
                self.assertEqual(
                    {wallet_a, wallet_b},
                    {row[0] for row in connection.execute(
                        "select wallet_address from pipeline_metadata"
                    ).fetchall()},
                )
                override_row = connection.execute(
                    "select status from app.token_recognition_overrides where token_address = ?",
                    [token],
                ).fetchone()
                if override_row is None:
                    self.fail("token override was not preserved")
                self.assertEqual(override_row[0], "recognized")
                self.assertEqual(
                    connection.execute(
                        "select generated_at from pipeline_metadata where wallet_address = ?",
                        [wallet_a],
                    ).fetchone(),
                    (datetime(2026, 8, 10, tzinfo=timezone.utc),),
                )
            self.assertEqual({row["wallet_address"] for row in manager.list_wallets()}, {wallet_a, wallet_b})

    def test_scan_extension_accepts_cumulative_snapshot_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            wallet = "0x" + "a" * 40
            with duckdb.connect(str(live)) as connection:
                for relation in ("wallet_events", "token_summary", "counterparty_summary", "timeline_daily"):
                    connection.execute(f"create table {relation} (wallet_address varchar)")
                connection.execute(
                    """
                    create table pipeline_metadata (
                      chain_id integer, wallet_address varchar, configured_wallet_label varchar,
                      data_source varchar,
                      snapshot_start_block bigint, snapshot_end_block bigint,
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar,
                      generated_at timestamptz
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', 0, 10, ?, 'ethereum_finalized', current_timestamp)",
                    [wallet, "0x" + "a" * 64],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                self.assertEqual(job.from_block, 11)
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute(
                        "update pipeline_metadata set snapshot_end_block = ?, snapshot_end_block_hash = ? where wallet_address = ?",
                        [job.to_block, "0x" + "b" * 64, wallet],
                    )
                progress(90)

            manager = ScanJobManager(
                live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 20
            )
            # The dashboard query service keeps read-write connections because
            # it owns recognition overrides. Manager reads and validation must
            # use the same DuckDB configuration while one is active.
            with duckdb.connect(str(live), read_only=False):
                self.assertEqual(
                    {item["wallet_address"] for item in manager.list_wallets()},
                    {wallet},
                )
                self.assertEqual(manager._next_from_block(wallet), 11)
            job = manager.create(wallet)
            for _ in range(50):
                current = manager.get(job.job_id)
                if current and current.status in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            completed = manager.get(job.job_id)
            assert completed is not None
            self.assertEqual(completed.status, "completed", completed.error)
            self.assertEqual((completed.from_block, completed.to_block), (11, 20))
            with duckdb.connect(str(live), read_only=True) as connection:
                self.assertEqual(
                    connection.execute(
                        "select snapshot_start_block, snapshot_end_block from pipeline_metadata where wallet_address = ?",
                        [wallet],
                    ).fetchone(),
                    (0, 20),
                )

    def test_validation_accepts_generated_at_metadata_schema_upgrade(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous.duckdb"
            staging = Path(directory) / "staging.duckdb"
            wallet_a = "0x" + "a" * 40
            wallet_b = "0x" + "b" * 40
            with duckdb.connect(str(previous)) as connection:
                for relation in (
                    "wallet_events", "token_summary", "counterparty_summary", "timeline_daily"
                ):
                    connection.execute(f"create table {relation} (wallet_address varchar)")
                connection.execute(
                    """
                    create table pipeline_metadata (
                      chain_id integer, wallet_address varchar, configured_wallet_label varchar,
                      data_source varchar,
                      snapshot_start_block bigint, snapshot_end_block bigint,
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', 0, 10, ?, 'ethereum_finalized')",
                    [wallet_a, "0x" + "a" * 64],
                )
            shutil.copy2(previous, staging)
            with duckdb.connect(str(staging)) as connection:
                connection.execute(
                    "alter table pipeline_metadata add column generated_at timestamptz"
                )
                connection.execute(
                    "update pipeline_metadata set generated_at = timestamptz '2026-08-10 00:00:00+00'"
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-b', 'hyperindex', 0, 20, ?, 'ethereum_finalized', timestamptz '2026-08-10 00:00:00+00')",
                    [wallet_b, "0x" + "b" * 64],
                )

            job = ScanJob(
                "job", wallet_b, wallet_b, wallet_b, "running", 95, 0, 20, None,
                "2026-08-10T00:00:00+00:00", "2026-08-10T00:00:00+00:00",
            )
            ScanJobManager._validate_staged_artifact(job, staging, previous)

    def test_scan_extension_rejects_changed_cumulative_snapshot_start(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            wallet = "0x" + "a" * 40
            with duckdb.connect(str(live)) as connection:
                for relation in ("wallet_events", "token_summary", "counterparty_summary", "timeline_daily"):
                    connection.execute(f"create table {relation} (wallet_address varchar)")
                connection.execute(
                    """
                    create table pipeline_metadata (
                      chain_id integer, wallet_address varchar, configured_wallet_label varchar,
                      data_source varchar,
                      snapshot_start_block bigint, snapshot_end_block bigint,
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar,
                      generated_at timestamptz
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', 0, 10, ?, 'ethereum_finalized', current_timestamp)",
                    [wallet, "0x" + "a" * 64],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute(
                        "update pipeline_metadata set snapshot_start_block = ?, snapshot_end_block = ?, snapshot_end_block_hash = ? where wallet_address = ?",
                        [1, job.to_block, "0x" + "b" * 64, wallet],
                    )
                progress(90)

            manager = ScanJobManager(
                live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 20
            )
            job = manager.create(wallet)
            for _ in range(50):
                current = manager.get(job.job_id)
                if current and current.status in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            failed = manager.get(job.job_id)
            assert failed is not None
            self.assertEqual(failed.status, "failed")
            self.assertIn("does not cover the requested block range", failed.error or "")
            with duckdb.connect(str(live), read_only=True) as connection:
                self.assertEqual(
                    connection.execute(
                        "select snapshot_start_block, snapshot_end_block from pipeline_metadata where wallet_address = ?",
                        [wallet],
                    ).fetchone(),
                    (0, 10),
                )

    def test_scan_rejects_worker_that_drops_existing_wallet_rows(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            wallet_a = "0x" + "a" * 40
            wallet_b = "0x" + "b" * 40
            with duckdb.connect(str(live)) as connection:
                connection.execute("create table wallet_events (wallet_address varchar, event_id varchar)")
                connection.execute("insert into wallet_events values (?, 'event-a')", [wallet_a])
                for relation in ("token_summary", "counterparty_summary", "timeline_daily"):
                    connection.execute(f"create table {relation} (wallet_address varchar)")
                connection.execute(
                    """
                    create table pipeline_metadata (
                      chain_id integer, wallet_address varchar, configured_wallet_label varchar,
                      data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint,
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar,
                      generated_at timestamptz
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', 0, 10, ?, 'ethereum_finalized', current_timestamp)",
                    [wallet_a, "0x" + "a" * 64],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                del progress
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute("delete from wallet_events")
                    connection.execute(
                        "insert into pipeline_metadata values (1, ?, 'wallet-b', 'hyperindex', 0, 20, ?, 'ethereum_finalized', current_timestamp)",
                        [wallet_b, "0x" + "b" * 64],
                    )

            manager = ScanJobManager(
                live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 20
            )
            job = manager.create(wallet_b)
            for _ in range(50):
                current = manager.get(job.job_id)
                if current and current.status == "failed":
                    break
                time.sleep(0.01)
            failed = manager.get(job.job_id)
            assert failed is not None
            self.assertEqual(failed.status, "failed")
            self.assertIn("dropped rows from wallet_events", failed.error or "")
            with duckdb.connect(str(live), read_only=True) as connection:
                event_row = connection.execute("select event_id from wallet_events").fetchone()
                if event_row is None:
                    self.fail("existing event was not preserved")
                self.assertEqual(event_row[0], "event-a")

    def test_scan_accepts_recomputed_summary_rows_when_event_identity_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            wallet = "0x" + "a" * 40
            transaction_hash = "0x" + "1" * 64
            with duckdb.connect(str(live)) as connection:
                connection.execute(
                    """
                    create table wallet_events (
                      chain_id integer, wallet_address varchar,
                      transaction_hash varchar, log_index integer
                    )
                    """
                )
                connection.execute(
                    "insert into wallet_events values (1, ?, ?, 0)",
                    [wallet, transaction_hash],
                )
                connection.execute(
                    "create table token_summary (wallet_address varchar, transfer_count bigint)"
                )
                connection.execute("insert into token_summary values (?, 1)", [wallet])
                for relation in ("counterparty_summary", "timeline_daily"):
                    connection.execute(f"create table {relation} (wallet_address varchar)")
                connection.execute(
                    """
                    create table pipeline_metadata (
                      chain_id integer, wallet_address varchar, configured_wallet_label varchar,
                      data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint,
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar,
                      generated_at timestamptz
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', 0, 10, ?, 'ethereum_finalized', current_timestamp)",
                    [wallet, "0x" + "a" * 64],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                del progress
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute("update token_summary set transfer_count = 2")
                    connection.execute(
                        "update pipeline_metadata set snapshot_end_block = ?, snapshot_end_block_hash = ? where wallet_address = ?",
                        [job.to_block, "0x" + "b" * 64, wallet],
                    )

            manager = ScanJobManager(
                live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 20
            )
            job = manager.create(wallet)
            for _ in range(500):
                current = manager.get(job.job_id)
                if current and current.status in {"completed", "failed"}:
                    break
                time.sleep(0.01)
            completed = manager.get(job.job_id)
            assert completed is not None
            self.assertEqual(completed.status, "completed", completed.error)
            with duckdb.connect(str(live), read_only=True) as connection:
                self.assertEqual(
                    connection.execute("select transfer_count from token_summary").fetchone(),
                    (2,),
                )
                self.assertEqual(
                    connection.execute(
                        "select transaction_hash from wallet_events"
                    ).fetchone(),
                    (transaction_hash,),
                )

    def test_failed_worker_leaves_previous_artifact_served(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            with duckdb.connect(str(live)) as connection:
                connection.execute("create table marker (value varchar)")
                connection.execute("insert into marker values ('safe')")

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                del job, staging_path, progress
                raise RuntimeError("provider unavailable")

            manager = ScanJobManager(live, resolver=resolve_wallet, worker=worker, finalized_head=lambda: 5)
            job = manager.create("vitalik.eth")
            for _ in range(50):
                current = manager.get(job.job_id)
                if current and current.status == "failed":
                    break
                time.sleep(0.01)
            failed = manager.get(job.job_id)
            assert failed is not None
            self.assertEqual(failed.status, "failed")
            with duckdb.connect(str(live), read_only=True) as connection:
                row = connection.execute("select value from marker").fetchone()
                assert row is not None
                self.assertEqual(row[0], "safe")

    def test_resolves_configured_ens_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                del job, staging_path, progress
            manager = ScanJobManager(Path(directory) / "live.duckdb", resolver=resolve_wallet, worker=worker, finalized_head=lambda: 1)
            assert manager.resolver is not None
            address, label = manager.resolver("vitalik.eth")
            self.assertEqual(address, "0xd8da6bf26964af9d7eed9e03e53415d37aa96045")
            self.assertEqual(label, "vitalik.eth")

    def test_legacy_resolver_does_not_impersonate_live_ens_resolution(self) -> None:
        with self.assertRaisesRegex(ValueError, "legacy/test adapter"):
            resolve_wallet("wallet.eth")

    def test_rejects_artifact_from_different_finalized_chain_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            live = Path(directory) / "live.duckdb"
            observation = ResolvedScanInput(
                "wallet.eth", "wallet.eth", "0x" + "1" * 40, "ens-registry:test",
                123, "0x" + "a" * 64, datetime(2026, 1, 2, tzinfo=timezone.utc),
            )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                del progress
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute("create table wallet_events (wallet_address varchar)")
                    connection.execute("create table token_summary (wallet_address varchar)")
                    connection.execute("create table counterparty_summary (wallet_address varchar)")
                    connection.execute("create table timeline_daily (wallet_address varchar)")
                    connection.execute(
                        "create table pipeline_metadata (wallet_address varchar, data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint, snapshot_end_block_hash varchar, snapshot_finality_policy varchar, generated_at timestamptz)"
                    )
                    connection.execute(
                        "insert into pipeline_metadata values (?, 'hyperindex', 0, ?, ?, 'ethereum_finalized', current_timestamp)",
                        [job.wallet_address, job.to_block, "0x" + "b" * 64],
                    )

            manager = ScanJobManager(
                live,
                scan_input_resolver=lambda value: observation,
                worker=worker,
            )
            job = manager.create("wallet.eth")
            for _ in range(50):
                current = manager.get(job.job_id)
                if current and current.status == "failed":
                    break
                time.sleep(0.01)
            failed = manager.get(job.job_id)
            assert failed is not None
            self.assertEqual(failed.status, "failed")
            self.assertIn("block hash", failed.error or "")


if __name__ == "__main__":
    unittest.main()
