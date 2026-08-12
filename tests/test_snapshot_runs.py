import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from scripts.snapshot_runs import (
    ConfiguredWallet,
    FinalizedBlock,
    HyperIndexMetadata,
    SnapshotAlreadyCurrent,
    SnapshotRun,
    dbt_snapshot_environment,
    ensure_run_table,
    fetch_hyperindex_metadata,
    finish_snapshot_run,
    latest_completed_snapshot_run,
    mark_ingestion_complete,
    next_run_start,
    resolve_finalized_block,
    resolve_snapshot_target,
    start_snapshot_run,
    start_snapshot_runs,
)
from server.ens import ResolvedScanInput

WALLET = ConfiguredWallet(
    address="0x4444444444444444444444444444444444444444",
    label="wallet.eth",
)


class FakeRpcClient:
    def call(self, method, params):
        if method != "eth_getBlockByNumber" or params != ["finalized", False]:
            raise AssertionError((method, params))
        return {"number": "0x64", "hash": "0x" + "a" * 64}


class LaggingRpcClient:
    def call(self, method, params):
        if method != "eth_getBlockByNumber":
            raise AssertionError((method, params))
        if params == ["finalized", False]:
            return {"number": "0x64", "hash": "0x" + "a" * 64}
        if params == ["0x4b", False]:
            return {"number": "0x4b", "hash": "0x" + "b" * 64}
        raise AssertionError(params)


class SnapshotRunsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "live.duckdb"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_pipeline_run_table_has_exact_contract(self) -> None:
        with duckdb.connect(str(self.database_path)) as connection:
            ensure_run_table(connection)
            actual = [
                (row[1], row[2], bool(row[3]), bool(row[5]))
                for row in connection.execute(
                    "pragma table_info('ops.pipeline_runs')"
                ).fetchall()
            ]

        self.assertEqual(
            actual,
            [
                ("run_id", "VARCHAR", True, True),
                ("chain_id", "INTEGER", True, False),
                ("generation_id", "VARCHAR", True, False),
                ("wallet_address", "VARCHAR", True, False),
                ("wallet_label", "VARCHAR", True, False),
                ("from_block", "BIGINT", True, False),
                ("to_block", "BIGINT", True, False),
                ("to_block_hash", "VARCHAR", True, False),
                ("events_found", "BIGINT", False, False),
                ("status", "VARCHAR", True, False),
                ("completed_at", "TIMESTAMP WITH TIME ZONE", False, False),
                ("scope_version", "VARCHAR", True, False),
                ("original_input", "VARCHAR", False, False),
                ("normalized_name", "VARCHAR", False, False),
                ("resolver_source", "VARCHAR", False, False),
                ("observation_block_number", "BIGINT", False, False),
                ("observation_block_hash", "VARCHAR", False, False),
                ("observation_timestamp", "TIMESTAMP WITH TIME ZONE", False, False),
                ("ingestion_status", "VARCHAR", True, False),
                ("raw_events_found", "BIGINT", False, False),
                ("raw_ingested_at", "TIMESTAMP WITH TIME ZONE", False, False),
            ],
        )

    def test_pipeline_run_keeps_ingestion_checkpoint_separate_from_publication(self) -> None:
        run = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        mark_ingestion_complete(run, raw_events_found=4, database_path=self.database_path)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            row = connection.execute(
                "select status, ingestion_status, raw_events_found, raw_ingested_at from ops.pipeline_runs where run_id = ?",
                [run.run_id],
            ).fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row[0:3], ("running", "completed", 4))
        self.assertIsNotNone(row[3])

    def test_failed_publication_reuses_completed_ingestion_without_new_run(self) -> None:
        run = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        mark_ingestion_complete(run, raw_events_found=4, database_path=self.database_path)
        finish_snapshot_run(run, database_path=self.database_path, succeeded=False)
        retry = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        self.assertEqual(retry.run_id, run.run_id)
        self.assertEqual(retry.from_block, run.from_block)
        with duckdb.connect(str(self.database_path), read_only=True) as connection:
            row = connection.execute("select count(*) from ops.pipeline_runs").fetchone()
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row[0], 1)

    def test_wallet_targets_use_composite_identity(self) -> None:
        with duckdb.connect(str(self.database_path)) as connection:
            ensure_run_table(connection)
            actual = [
                (row[1], row[2], bool(row[3]), bool(row[5]))
                for row in connection.execute(
                    "pragma table_info('ops.wallet_targets')"
                ).fetchall()
            ]

        self.assertEqual(
            actual,
            [
                ("chain_id", "INTEGER", True, True),
                ("wallet_address", "VARCHAR", True, True),
                ("wallet_label", "VARCHAR", True, False),
                ("created_at", "TIMESTAMP WITH TIME ZONE", True, False),
            ],
        )

    def test_reads_transactional_hyperindex_progress_and_finalized_rpc_block(self) -> None:
        def transport(_url, payload):
            self.assertEqual(payload["variables"], {"chainId": 1})
            return {
                "data": {
                    "_meta": [{
                        "chainId": 1,
                        "progressBlock": 120,
                        "startBlock": 3,
                        "endBlock": None,
                        "isReady": True,
                    }]
                }
            }

        metadata = fetch_hyperindex_metadata("http://hyperindex.test/graphql", transport=transport)
        finalized = resolve_finalized_block(FakeRpcClient())

        self.assertEqual(metadata, HyperIndexMetadata(3, 120, None, True))
        self.assertEqual(finalized, FinalizedBlock(100, "0x" + "a" * 64))

    def test_caps_snapshot_at_indexed_progress_when_indexer_lags_finality(self) -> None:
        target = resolve_snapshot_target(
            LaggingRpcClient(),
            HyperIndexMetadata(3, 75, None, False),
        )

        self.assertEqual(target, FinalizedBlock(75, "0x" + "b" * 64))

    def test_caps_snapshot_at_configured_indexer_end(self) -> None:
        target = resolve_snapshot_target(
            LaggingRpcClient(),
            HyperIndexMetadata(3, 90, 75, True),
        )

        self.assertEqual(target, FinalizedBlock(75, "0x" + "b" * 64))

    def test_records_one_run_per_contiguous_finalized_interval(self) -> None:
        first = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        self.assertEqual((first.from_block, first.to_block), (3, 75))

        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute(
                "create table wallet_events (chain_id integer, wallet_address varchar, block_number bigint)"
            )
            connection.execute(
                "insert into wallet_events values (1, ?, 50), (1, ?, 70)",
                [WALLET.address, WALLET.address],
            )
        finish_snapshot_run(first, database_path=self.database_path, succeeded=True)

        second = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 120, None, True),
            finalized_block=FinalizedBlock(100, "0x" + "b" * 64),
        )
        self.assertEqual((second.from_block, second.to_block), (76, 100))

        with duckdb.connect(str(self.database_path)) as connection:
            first_row = connection.execute(
                "select events_found, status from ops.pipeline_runs where run_id = ?",
                [first.run_id],
            ).fetchone()
            self.assertEqual(first_row, (2, "completed"))

    def test_persists_scan_input_resolution_provenance_in_selected_wallet_run(self) -> None:
        resolved = ResolvedScanInput(
            " Wallet.ETH ",
            "wallet.eth",
            WALLET.address,
            "ens-registry:0xregistry/resolver:0xresolver",
            75,
            "0x" + "c" * 64,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        run = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
            scan_input=resolved,
        )
        with duckdb.connect(str(self.database_path)) as connection:
            row = connection.execute(
                """
                select original_input, normalized_name, wallet_address, resolver_source,
                  observation_block_number, observation_block_hash, observation_timestamp
                from ops.pipeline_runs where run_id = ?
                """,
                [run.run_id],
            ).fetchone()
        self.assertEqual(row, (
            " Wallet.ETH ", "wallet.eth", WALLET.address,
            "ens-registry:0xregistry/resolver:0xresolver", 75, "0x" + "c" * 64,
            datetime(2026, 1, 2, tzinfo=timezone.utc),
        ))

    def test_first_scan_of_new_wallet_is_independent_from_existing_wallet_progress(self) -> None:
        second_wallet = ConfiguredWallet("0x" + "1" * 40, "second")
        first = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(100, "0x" + "a" * 64),
        )
        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute(
                "create table wallet_events (chain_id integer, wallet_address varchar, block_number bigint)"
            )
            connection.execute("insert into wallet_events values (1, ?, 50)", [WALLET.address])
        finish_snapshot_run(first, database_path=self.database_path, succeeded=True)

        runs = start_snapshot_runs(
            database_path=self.database_path,
            wallets=[WALLET, second_wallet],
            metadata=HyperIndexMetadata(3, 200, None, True),
            finalized_block=FinalizedBlock(150, "0x" + "b" * 64),
        )
        self.assertEqual(len(runs), 2)
        by_wallet = {run.wallet_address: run for run in runs}
        self.assertEqual((by_wallet[WALLET.address].from_block, by_wallet[WALLET.address].to_block), (101, 150))
        self.assertEqual((by_wallet[second_wallet.address].from_block, by_wallet[second_wallet.address].to_block), (3, 150))
        self.assertNotEqual(runs[0].generation_id, runs[1].generation_id)

        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute("insert into wallet_events values (1, ?, 120), (1, ?, 50)", [WALLET.address, second_wallet.address])
        for run in runs:
            finish_snapshot_run(run, database_path=self.database_path, succeeded=True)
        with duckdb.connect(str(self.database_path)) as connection:
            target_rows = connection.execute("select chain_id, wallet_address from ops.wallet_targets order by wallet_address").fetchall()
            generation_rows = connection.execute(
                "select wallet_address, count(*) from ops.scan_generations group by wallet_address order by wallet_address"
            ).fetchall()
        self.assertEqual(target_rows, [(1, second_wallet.address), (1, WALLET.address)])
        self.assertEqual(generation_rows, [(second_wallet.address, 1), (WALLET.address, 2)])

    def test_existing_wallet_incremental_refresh_preserves_prior_run(self) -> None:
        first = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(100, "0x" + "a" * 64),
        )
        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute("create table wallet_events (chain_id integer, wallet_address varchar, block_number bigint)")
            connection.execute("insert into wallet_events values (1, ?, 50)", [WALLET.address])
        finish_snapshot_run(first, database_path=self.database_path, succeeded=True)
        second = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 200, None, True),
            finalized_block=FinalizedBlock(150, "0x" + "b" * 64),
        )
        self.assertEqual(second.from_block, 101)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertNotEqual(first.generation_id, second.generation_id)
        with duckdb.connect(str(self.database_path)) as connection:
            rows = connection.execute(
                "select run_id, status from ops.pipeline_runs order by from_block"
            ).fetchall()
        self.assertEqual(rows, [(first.run_id, "completed"), (second.run_id, "running")])

    def test_dbt_environment_separates_missing_interval_from_cumulative_coverage(self) -> None:
        run = SnapshotRun(
            run_id="run",
            chain_id=1,
            wallet_address=WALLET.address,
            wallet_label=WALLET.label,
            from_block=101,
            to_block=150,
            to_block_hash="0x" + "a" * 64,
            scope_version="wallet-transfer-signature-v1",
            generation_id="generation",
        )
        environment = dbt_snapshot_environment(run)
        self.assertEqual(environment["EVM_WALLET_SNAPSHOT_START_BLOCK"], "101")
        self.assertNotIn("EVM_WALLET_SNAPSHOT_COVERAGE_START_BLOCK", environment)

    def test_refuses_gaps_stale_indexer_and_empty_increment(self) -> None:
        with duckdb.connect(str(self.database_path)) as connection:
            ensure_run_table(connection)
            connection.execute(
                """
                insert into ops.pipeline_runs (
                  run_id, chain_id, generation_id, wallet_address, wallet_label, from_block, to_block,
                  to_block_hash, events_found, status, completed_at, scope_version
                ) values (
                  'gap', 1, 'generation-gap', ?, 'wallet.eth', 4, 10, ?, 0, 'completed', current_timestamp, ?
                )
                """,
                [WALLET.address, "0x" + "a" * 64, "wallet-transfer-signature-v1"],
            )
            with self.assertRaisesRegex(RuntimeError, "not contiguous"):
                next_run_start(
                    connection,
                    chain_id=1,
                    wallet_address=WALLET.address,
                    scope_version="wallet-transfer-signature-v1",
                    configured_start_block=3,
                )

        with self.assertRaisesRegex(RuntimeError, "has not fully processed"):
            start_snapshot_run(
                database_path=Path(self.temporary_directory.name) / "stale.duckdb",
                wallet=WALLET,
                metadata=HyperIndexMetadata(3, 74, None, False),
                finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
            )

        current_path = Path(self.temporary_directory.name) / "current.duckdb"
        run = start_snapshot_run(
            database_path=current_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 75, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        with duckdb.connect(str(current_path)) as connection:
            connection.execute(
                "create table wallet_events (chain_id integer, wallet_address varchar, block_number bigint)"
            )
        finish_snapshot_run(run, database_path=current_path, succeeded=True)
        with self.assertRaises(SnapshotAlreadyCurrent):
            start_snapshot_run(
                database_path=current_path,
                wallet=WALLET,
                metadata=HyperIndexMetadata(3, 75, None, True),
                finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
            )
        current = latest_completed_snapshot_run(
            database_path=current_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 75, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        self.assertEqual(current.run_id, run.run_id)

    def test_failed_run_remains_retryable(self) -> None:
        run = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        finish_snapshot_run(run, database_path=self.database_path, succeeded=False)
        retry = start_snapshot_run(
            database_path=self.database_path,
            wallet=WALLET,
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        self.assertEqual(retry.from_block, 3)


if __name__ == "__main__":
    unittest.main()
