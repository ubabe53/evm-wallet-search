import tempfile
import unittest
from pathlib import Path

import duckdb

from scripts.snapshot_runs import (
    ConfiguredWallet,
    FinalizedBlock,
    HyperIndexMetadata,
    SnapshotAlreadyCurrent,
    ensure_run_table,
    fetch_hyperindex_metadata,
    finish_snapshot_run,
    latest_completed_snapshot_run,
    next_run_start,
    resolve_finalized_block,
    resolve_snapshot_target,
    start_snapshot_run,
    start_snapshot_runs,
)

WALLET = ConfiguredWallet(
    address="0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
    label="vitalik.eth",
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

    def test_multi_wallet_run_shares_generation_and_keeps_wallet_grains(self) -> None:
        second_wallet = ConfiguredWallet("0x" + "1" * 40, "second")
        runs = start_snapshot_runs(
            database_path=self.database_path,
            wallets=[WALLET, second_wallet],
            metadata=HyperIndexMetadata(3, 100, None, True),
            finalized_block=FinalizedBlock(75, "0x" + "a" * 64),
        )
        self.assertEqual(len(runs), 2)
        self.assertEqual(runs[0].generation_id, runs[1].generation_id)
        with duckdb.connect(str(self.database_path)) as connection:
            connection.execute(
                "create table wallet_events (chain_id integer, wallet_address varchar, block_number bigint)"
            )
            connection.execute("insert into wallet_events values (1, ?, 50)", [WALLET.address])
        for run in runs:
            finish_snapshot_run(run, database_path=self.database_path, succeeded=True)
        with duckdb.connect(str(self.database_path)) as connection:
            targets = connection.execute("select count(*) from ops.wallet_targets").fetchone()
            runs_count = connection.execute("select count(*) from ops.pipeline_runs").fetchone()
            generations = connection.execute("select count(*) from ops.scan_generations where status = 'completed'").fetchone()
            assert targets is not None and runs_count is not None and generations is not None
            self.assertEqual(targets[0], 2)
            self.assertEqual(runs_count[0], 2)
            self.assertEqual(generations[0], 1)

    def test_refuses_gaps_stale_indexer_and_empty_increment(self) -> None:
        with duckdb.connect(str(self.database_path)) as connection:
            ensure_run_table(connection)
            connection.execute(
                """
                insert into ops.pipeline_runs values (
                  'gap', 1, 'generation-gap', ?, 'vitalik.eth', 4, 10, ?, 0, 'completed', current_timestamp, ?
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
