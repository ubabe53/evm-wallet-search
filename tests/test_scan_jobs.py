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

            def worker(job, staging_path, progress: Callable[[int], None]) -> None:
                progress(40)
                with duckdb.connect(str(staging_path)) as connection:
                    connection.execute("create table marker (value varchar)")
                    connection.execute("insert into marker values (?)", [job.wallet_address])
                    connection.execute("create table wallet_events (wallet_address varchar)")
                    connection.execute("create table token_summary (wallet_address varchar)")
                    connection.execute("create table counterparty_summary (wallet_address varchar)")
                    connection.execute("create table timeline_daily (wallet_address varchar)")
                    connection.execute(
                        "create table pipeline_metadata (wallet_address varchar, data_source varchar, snapshot_start_block bigint, snapshot_end_block bigint, snapshot_end_block_hash varchar, snapshot_finality_policy varchar)"
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
            self.assertEqual(completed.status, "completed")
            with duckdb.connect(str(live), read_only=True) as connection:
                row = connection.execute("select value from marker").fetchone()
                assert row is not None
                self.assertEqual(row[0], "0x" + "1" * 40)
            self.assertEqual(completed.from_block, 0)
            self.assertEqual(completed.to_block, 123)

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
                scan_input_resolver=lambda _value: observation,
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
