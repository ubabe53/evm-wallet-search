import unittest
from unittest.mock import MagicMock, patch

from scripts.wallet_scan_raw import (
    RawIngestionInterval,
    bounded_indexer_completed,
    completed_ingestion_prefix,
    drop_temporary_schema,
    merge_sql,
    public_raw_store_exists,
    shared_raw_store_exists,
    validate_indexer_checkpoint,
    validate_temporary_schema,
    verify_finalized_hash,
)


class WalletScanRawTest(unittest.TestCase):
    def setUp(self) -> None:
        self.interval = RawIngestionInterval(
            wallet_address="0x" + "a" * 40,
            from_block=101,
            to_block=200,
            to_block_hash="0x" + "b" * 64,
        )

    def test_merge_is_wallet_range_scoped_and_idempotent(self) -> None:
        sql = merge_sql("wallet_scan_job_123", self.interval)

        self.assertIn("from wallet_scan_job_123.\"Erc20Transfer\"", sql)
        self.assertIn("block_number < 101", sql)
        self.assertIn("block_number > 200", sql)
        self.assertIn("primary key (chain_id, transaction_hash, log_index)", sql)
        self.assertIn("on conflict (chain_id, transaction_hash, log_index) do nothing", sql)
        self.assertIn("existing.block_timestamp is distinct from incoming.block_timestamp", sql)
        self.assertIn("existing.transaction_index is distinct from incoming.transaction_index", sql)
        self.assertIn("existing.transaction_from_address is distinct from lower(incoming.transaction_from_address)", sql)
        self.assertIn("wallet_scan.ingestion_runs", sql)
        self.assertIn("different finalized hash", sql)
        self.assertIn("from wallet_scan_job_123.envio_chains", sql)
        self.assertIn("progress_block >= 200", sql)
        self.assertIn("ready_at is not null", sql)

    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_raw_store_detection_uses_exact_postgres_relations(self, connect) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (1,)

        self.assertTrue(public_raw_store_exists("postgresql://test"))
        self.assertEqual(connection.execute.call_args.args[1], ["public", "Erc20Transfer"])

        self.assertTrue(shared_raw_store_exists("postgresql://test"))
        self.assertEqual(
            connection.execute.call_args.args[1],
            ["wallet_scan", "transfer_events"],
        )

    def test_rejects_persistent_or_unsafe_temporary_schema(self) -> None:
        for schema in ("public", "wallet_scan", "wallet_scan_job;drop schema public"):
            with self.subTest(schema=schema), self.assertRaises(ValueError):
                validate_temporary_schema(schema)

    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_schema_cleanup_uses_named_postgres_transaction_argument(self, connect) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection

        drop_temporary_schema("postgresql://test", "wallet_scan_job_123")

        self.assertEqual(
            connection.execute.call_args.args[0],
            "call postgres_execute('shared', ?, use_transaction := true)",
        )

    @patch("scripts.wallet_scan_raw.shared_raw_store_exists", return_value=True)
    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_reuses_contiguous_completed_ingestion_prefix(self, connect, _exists) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            (101, 150, "0x" + "c" * 64, 2),
            (151, 175, "0x" + "d" * 64, 3),
        ]

        self.assertEqual(
            completed_ingestion_prefix("postgresql://test", self.interval),
            (176, 5),
        )

    @patch("scripts.wallet_scan_raw.shared_raw_store_exists", return_value=True)
    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_reuses_exact_completed_endpoint_with_matching_hash(self, connect, _exists) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            (101, 200, self.interval.to_block_hash, 4)
        ]

        self.assertEqual(
            completed_ingestion_prefix("postgresql://test", self.interval),
            (201, 4),
        )

    @patch("scripts.wallet_scan_raw.shared_raw_store_exists", return_value=True)
    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_rejects_gapped_or_overlapping_completed_prefix(self, connect, _exists) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        for rows in (
            [(102, 150, "0x" + "c" * 64, 2)],
            [
                (101, 150, "0x" + "c" * 64, 2),
                (150, 175, "0x" + "d" * 64, 3),
            ],
            [(101, 201, "0x" + "c" * 64, 4)],
        ):
            connection.execute.return_value.fetchall.return_value = rows
            with self.subTest(rows=rows), self.assertRaisesRegex(RuntimeError, "contiguous"):
                completed_ingestion_prefix("postgresql://test", self.interval)

    @patch("scripts.wallet_scan_raw.shared_raw_store_exists", return_value=True)
    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_rejects_completed_endpoint_with_different_finalized_hash(
        self, connect, _exists
    ) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.fetchall.return_value = [
            (101, 200, "0x" + "c" * 64, 4)
        ]

        with self.assertRaisesRegex(RuntimeError, "endpoint hash"):
            completed_ingestion_prefix("postgresql://test", self.interval)

    def test_rejects_invalid_interval_provenance(self) -> None:
        invalid = RawIngestionInterval(
            wallet_address="0x" + "a" * 40,
            from_block=200,
            to_block=100,
            to_block_hash="0x" + "b" * 64,
        )
        with self.assertRaisesRegex(ValueError, "from_block"):
            invalid.validate()

    def test_requires_authoritative_finalized_endpoint_hash(self) -> None:
        verify_finalized_hash(self.interval, lambda block: self.interval.to_block_hash)

        with self.assertRaisesRegex(RuntimeError, "no longer matches"):
            verify_finalized_hash(self.interval, lambda block: "0x" + "c" * 64)

        with self.assertRaisesRegex(RuntimeError, "invalid hash"):
            verify_finalized_hash(self.interval, lambda block: "not-a-hash")

    def test_requires_complete_bounded_indexer_checkpoint_even_for_empty_events(self) -> None:
        validate_indexer_checkpoint((1, 101, 200, 200, "completed-at"), self.interval)

        incomplete_rows = (
            None,
            (1, 101, 200, 199, None),
            (1, 101, 200, 200, None),
            (1, 102, 200, 200, "completed-at"),
            (1, 101, 201, 201, "completed-at"),
        )
        for row in incomplete_rows:
            with self.subTest(row=row), self.assertRaisesRegex(RuntimeError, "indexer"):
                validate_indexer_checkpoint(row, self.interval)

    @patch("scripts.wallet_scan_raw.postgres_connection")
    def test_polls_missing_or_partial_envio_checkpoint_until_ready(self, connect) -> None:
        connection = MagicMock()
        connect.return_value.__enter__.return_value = connection
        connection.execute.return_value.fetchone.return_value = (0,)
        self.assertFalse(
            bounded_indexer_completed(
                "postgresql://test",
                schema_name="wallet_scan_job_123",
                interval=self.interval,
            )
        )

        connection.execute.return_value.fetchone.return_value = (1,)
        connection.execute.return_value.fetchall.return_value = [
            (1, 101, 200, 199, None)
        ]
        self.assertFalse(
            bounded_indexer_completed(
                "postgresql://test",
                schema_name="wallet_scan_job_123",
                interval=self.interval,
            )
        )

        connection.execute.return_value.fetchall.return_value = [
            (1, 101, 200, 200, "ready")
        ]
        self.assertTrue(
            bounded_indexer_completed(
                "postgresql://test",
                schema_name="wallet_scan_job_123",
                interval=self.interval,
            )
        )


if __name__ == "__main__":
    unittest.main()
