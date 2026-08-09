import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from scripts.rebuild_live_enrichment import (
    cumulative_wallet_rebuild_scopes,
    restore_unselected_wallets,
    validate_enrichment_rebuild,
)


class RebuildLiveEnrichmentTest(unittest.TestCase):
    def create_artifact(self, path: Path) -> None:
        wallet = "0x" + "1" * 40
        with duckdb.connect(str(path)) as connection:
            connection.execute("create schema ops")
            connection.execute("create schema app")
            connection.execute(
                """
                create table ops.pipeline_runs (
                  run_id varchar, chain_id integer, generation_id varchar,
                  wallet_address varchar, wallet_label varchar, from_block bigint,
                  to_block bigint, to_block_hash varchar, scope_version varchar,
                  original_input varchar, normalized_name varchar, resolver_source varchar,
                  observation_block_number bigint, observation_block_hash varchar,
                  observation_timestamp timestamptz, status varchar, completed_at timestamptz
                )
                """
            )
            for run_id, start, end in (("run-1", 0, 10), ("run-2", 11, 20)):
                connection.execute(
                    "insert into ops.pipeline_runs values (?, 1, ?, ?, 'wallet', ?, ?, ?, 'scope', ?, null, 'direct', ?, ?, ?, 'completed', ?)",
                    [
                        run_id,
                        f"generation-{run_id}",
                        wallet,
                        start,
                        end,
                        "0x" + str(end % 10) * 64,
                        wallet,
                        end,
                        "0x" + str(end % 10) * 64,
                        datetime.now(timezone.utc),
                        datetime.now(timezone.utc),
                    ],
                )
            connection.execute(
                "create table app.token_recognition_overrides (chain_id integer, token_address varchar, status varchar)"
            )
            connection.execute(
                "insert into app.token_recognition_overrides values (1, ?, 'recognized')",
                ["0x" + "2" * 40],
            )
            connection.execute(
                """
                create table int_wallet_transfer_events as select
                  1 as chain_id, ? as wallet_address, 5::bigint as block_number,
                  ? as block_hash, current_timestamp as block_timestamp,
                  ? as transaction_hash, 0 as transaction_index,
                  ? as transaction_from_address, ? as transaction_to_address,
                  0 as log_index, ? as token_address, ? as from_address,
                  ? as to_address, 'in' as direction, ? as counterparty_address,
                  '1' as value_raw, 'unknown' as counterparty_account_type
                """,
                [
                    wallet,
                    "0x" + "3" * 64,
                    "0x" + "4" * 64,
                    "0x" + "5" * 40,
                    wallet,
                    "0x" + "6" * 40,
                    "0x" + "5" * 40,
                    wallet,
                    "0x" + "5" * 40,
                ],
            )
            connection.execute(
                """
                create table pipeline_metadata as select
                  1 as chain_id, ? as wallet_address, 'hyperindex' as data_source,
                  'run-2' as snapshot_run_id, 0::bigint as snapshot_start_block,
                  20::bigint as snapshot_end_block, ? as snapshot_end_block_hash,
                  'ethereum_finalized' as snapshot_finality_policy,
                  'scope' as snapshot_scope_version, 1::bigint as transfer_count
                """,
                [wallet, "0x" + "0" * 64],
            )

    def test_rebuild_scope_revisits_history_before_the_latest_interval(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "live.duckdb"
            self.create_artifact(path)
            runs = cumulative_wallet_rebuild_scopes(path)

        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0].run_id, "run-2")
        # run-2 itself starts at 11; rebuilding starts at 0 so run-1 events
        # receive newly collected shared account evidence too.
        self.assertEqual((runs[0].from_block, runs[0].to_block), (0, 20))

    def test_validation_allows_only_account_evidence_projection_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous.duckdb"
            staged = Path(directory) / "staged.duckdb"
            self.create_artifact(previous)
            shutil.copy2(previous, staged)
            with duckdb.connect(str(staged)) as connection:
                connection.execute(
                    "update int_wallet_transfer_events set counterparty_account_type = 'contract'"
                )

            validate_enrichment_rebuild(staged, previous)
            with duckdb.connect(str(staged)) as connection:
                connection.execute("update int_wallet_transfer_events set value_raw = '2'")
            with self.assertRaisesRegex(RuntimeError, "immutable wallet event facts"):
                validate_enrichment_rebuild(staged, previous)

    def test_each_iteration_restores_every_unselected_wallet_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            previous = Path(directory) / "previous.duckdb"
            staged = Path(directory) / "staged.duckdb"
            self.create_artifact(previous)
            shutil.copy2(previous, staged)
            first_wallet = "0x" + "1" * 40
            second_wallet = "0x" + "7" * 40
            with duckdb.connect(str(previous)) as connection:
                for relation in (
                    "int_wallet_transfer_events",
                    "wallet_events",
                    "token_summary",
                    "counterparty_summary",
                    "timeline_daily",
                    "pipeline_metadata",
                ):
                    if relation not in {"int_wallet_transfer_events", "pipeline_metadata"}:
                        connection.execute(
                            f"create table {relation} as select * from pipeline_metadata where false"
                        )
                connection.execute(
                    "insert into int_wallet_transfer_events select * replace (? as wallet_address) from int_wallet_transfer_events limit 1",
                    [second_wallet],
                )
                connection.execute(
                    "insert into pipeline_metadata select * replace (? as wallet_address) from pipeline_metadata limit 1",
                    [second_wallet],
                )
                for relation in (
                    "wallet_events",
                    "token_summary",
                    "counterparty_summary",
                    "timeline_daily",
                ):
                    connection.execute(
                        f"insert into {relation} select * replace (? as wallet_address) from pipeline_metadata limit 1",
                        [second_wallet],
                    )
            shutil.copy2(previous, staged)
            with duckdb.connect(str(staged)) as connection:
                for relation in (
                    "int_wallet_transfer_events",
                    "wallet_events",
                    "token_summary",
                    "counterparty_summary",
                    "timeline_daily",
                    "pipeline_metadata",
                ):
                    connection.execute(
                        f"delete from {relation} where wallet_address = ?", [second_wallet]
                    )

            restore_unselected_wallets(staged, previous, first_wallet)

            with duckdb.connect(str(staged), read_only=True) as connection:
                for relation in (
                    "int_wallet_transfer_events",
                    "wallet_events",
                    "token_summary",
                    "counterparty_summary",
                    "timeline_daily",
                    "pipeline_metadata",
                ):
                    row = connection.execute(
                        f"select count(*) from {relation} where wallet_address = ?",
                        [second_wallet],
                    ).fetchone()
                    self.assertIsNotNone(row)
                    assert row is not None
                    self.assertEqual(row[0], 1, relation)


if __name__ == "__main__":
    unittest.main()
