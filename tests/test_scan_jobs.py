import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import duckdb

from server.ens import ResolvedScanInput
from server.scan_jobs import ScanJobManager, resolve_wallet


class ScanJobsTest(unittest.TestCase):
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
                        "create table if not exists pipeline_metadata (wallet_address varchar, data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint, snapshot_end_block_hash varchar, snapshot_finality_policy varchar)"
                    )
                    connection.execute(
                        "insert into pipeline_metadata values (?, 'hyperindex', 0, 123, '0xhash', 'ethereum_finalized')",
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
                        "insert into pipeline_metadata values (1, ?, 'wallet-b', 'hyperindex', ?, ?, ?, 'ethereum_finalized')",
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
            self.assertEqual({row["wallet_address"] for row in manager.list_wallets()}, {wallet_a, wallet_b})

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
                      snapshot_end_block_hash varchar, snapshot_finality_policy varchar
                    )
                    """
                )
                connection.execute(
                    "insert into pipeline_metadata values (1, ?, 'wallet-a', 'hyperindex', 0, 10, ?, 'ethereum_finalized')",
                    [wallet_a, "0x" + "a" * 64],
                )

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                del progress
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute("delete from wallet_events")
                    connection.execute(
                        "insert into pipeline_metadata values (1, ?, 'wallet-b', 'hyperindex', 0, 20, ?, 'ethereum_finalized')",
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
                        "create table pipeline_metadata (wallet_address varchar, data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint, snapshot_end_block_hash varchar, snapshot_finality_policy varchar)"
                    )
                    connection.execute(
                        "insert into pipeline_metadata values (?, 'hyperindex', 0, ?, ?, 'ethereum_finalized')",
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
