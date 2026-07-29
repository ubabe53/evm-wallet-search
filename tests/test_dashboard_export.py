import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import scripts.export_dashboard as dashboard_export


class DashboardExportTest(unittest.TestCase):
    def test_export_schema_requires_event_and_direction_evidence(self) -> None:
        duckdb = dashboard_export.ensure_duckdb()
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                "create table wallet_events (from_address varchar, to_address varchar, value_raw varchar)"
            )
            connection.execute(
                "create table token_summary (transfer_count integer, value_raw_sum varchar)"
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "wallet_events is missing required export columns",
            ):
                dashboard_export.validate_export_schema(connection)

            for column in (
                "transaction_from_address varchar",
                "transaction_to_address varchar",
                "transaction_sender_relation varchar",
                "transaction_target_relation varchar",
                "is_indirect boolean",
                "counterparty_account_type varchar",
            ):
                connection.execute(f"alter table wallet_events add column {column}")
            connection.execute(
                "alter table token_summary add column indirect_inbound_transfer_count integer"
            )
            connection.execute(
                "alter table token_summary add column indirect_outbound_transfer_count integer"
            )
            connection.execute(
                "alter table token_summary add column self_transfer_count integer"
            )
            for column in ("counterparty_account_type varchar",):
                connection.execute(f"alter table token_summary add column {column}")

            dashboard_export.validate_export_schema(connection)
        finally:
            connection.close()

    def test_counterparty_candidates_cover_combined_recognition_rankings(self) -> None:
        duckdb = dashboard_export.ensure_duckdb()
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                """
                create table counterparty_summary (
                    counterparty_address varchar,
                    recognition_status varchar,
                    account_type varchar,
                    transfer_count integer,
                    last_seen_at timestamp
                )
                """
            )
            connection.executemany(
                "insert into counterparty_summary values (?, ?, ?, ?, ?)",
                [
                    ("0xaaa", "recognized", "contract", 90, "2024-01-01"),
                    ("0xaaa", "other", "contract", 90, "2024-01-01"),
                    ("0xbbb", "recognized", "contract", 100, "2024-01-02"),
                    ("0xccc", "other", "contract", 100, "2024-01-02"),
                ],
            )

            exported = dashboard_export.counterparty_rows(
                connection,
                recognition_statuses=("recognized", "other"),
                ranking_limit=1,
            )
        finally:
            connection.close()

        exported_addresses = [row["counterparty_address"] for row in exported]
        self.assertEqual(exported_addresses.count("0xaaa"), 2)
        combined_counts: dict[str, int] = {}
        for row in exported:
            combined_counts[row["counterparty_address"]] = (
                combined_counts.get(row["counterparty_address"], 0) + row["transfer_count"]
            )
        self.assertEqual(max(combined_counts, key=lambda address: combined_counts[address]), "0xaaa")

    def test_counterparty_candidates_cover_all_nine_filter_selections_in_one_query(self) -> None:
        with patch.object(dashboard_export, "query_rows", return_value=[]) as query:
            self.assertEqual(dashboard_export.counterparty_rows(object()), [])

        recognition_combinations = dashboard_export.non_empty_subsets(
            dashboard_export.RECOGNITION_STATUSES
        )
        account_combinations = dashboard_export.non_empty_subsets(dashboard_export.ACCOUNT_FILTERS)
        self.assertEqual(len(recognition_combinations), 3)
        self.assertEqual(len(account_combinations), 3)
        self.assertEqual(len(recognition_combinations) * len(account_combinations), 9)
        self.assertEqual(query.call_count, 1)

    def test_full_binary_selection_retains_internal_unknown_rows(self) -> None:
        duckdb = dashboard_export.ensure_duckdb()
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                """
                create table counterparty_summary (
                    counterparty_address varchar,
                    recognition_status varchar,
                    account_type varchar,
                    transfer_count integer,
                    last_seen_at timestamp
                )
                """
            )
            connection.executemany(
                "insert into counterparty_summary values (?, ?, ?, ?, ?)",
                [
                    ("0xunknown", "recognized", "unknown", 200, "2025-01-03"),
                    ("0xcontract", "recognized", "contract", 150, "2025-01-02"),
                    ("0xeoa", "recognized", "eoa_candidate", 125, "2025-01-01"),
                ],
            )
            exported = dashboard_export.counterparty_rows(
                connection,
                recognition_statuses=("recognized",),
                account_filters=("eoa_candidate", "contract"),
                ranking_limit=1,
            )
        finally:
            connection.close()

        self.assertIn("0xunknown", {row["counterparty_address"] for row in exported})

    def test_token_candidates_rank_after_account_cell_aggregation(self) -> None:
        duckdb = dashboard_export.ensure_duckdb()
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                """
                create table token_summary (
                    token_address varchar,
                    recognition_status varchar,
                    counterparty_account_type varchar,
                    transfer_count integer,
                    token_symbol varchar
                )
                """
            )
            connection.executemany(
                "insert into token_summary values (?, ?, ?, ?, ?)",
                [
                    ("0xaaa", "recognized", "contract", 60, "A"),
                    ("0xaaa", "recognized", "eoa_candidate", 60, "A"),
                    ("0xbbb", "recognized", "contract", 100, "B"),
                    ("0xccc", "recognized", "eoa_candidate", 100, "C"),
                ],
            )

            exported = dashboard_export.token_summary_rows(
                connection,
                recognition_statuses=("recognized",),
                account_filters=("contract", "eoa_candidate"),
                ranking_limit=1,
            )
        finally:
            connection.close()

        exported_addresses = [row["token_address"] for row in exported]
        self.assertEqual(exported_addresses.count("0xaaa"), 2)

    def test_token_candidates_cover_all_filter_selections_in_one_query(self) -> None:
        with patch.object(dashboard_export, "query_rows", return_value=[]) as query:
            self.assertEqual(dashboard_export.token_summary_rows(object()), [])

        self.assertEqual(query.call_count, 1)

    def test_graph_label_exposes_only_public_binary_types(self) -> None:
        label = dashboard_export.display_label({
            "node_type": "counterparty",
            "label": "0x3333333333333333333333333333333333333333",
            "account_type": "eoa_candidate",
        })
        self.assertEqual(label, "0x3333...3333\nEOA")

    def test_sampling_covers_every_bounded_export(self) -> None:
        metadata = {
            "exported_event_count": 10,
            "transfer_count": 10,
            "exported_interaction_count": 8,
            "interaction_count": 8,
            "exported_token_summary_count": 6,
            "token_summary_row_count": 6,
            "exported_counterparty_summary_count": 4,
            "counterparty_summary_row_count": 4,
            "exported_timeline_row_count": 2,
            "timeline_row_count": 2,
        }
        self.assertFalse(dashboard_export.export_is_sampled(metadata))

        for exported, complete in (
            ("exported_event_count", "transfer_count"),
            ("exported_interaction_count", "interaction_count"),
            ("exported_token_summary_count", "token_summary_row_count"),
            ("exported_counterparty_summary_count", "counterparty_summary_row_count"),
            ("exported_timeline_row_count", "timeline_row_count"),
        ):
            with self.subTest(complete=complete):
                sampled = dict(metadata)
                sampled[exported] -= 1
                self.assertTrue(dashboard_export.export_is_sampled(sampled))

    def test_json_replacement_leaves_a_complete_file(self) -> None:
        with TemporaryDirectory() as directory:
            original_public_data = dashboard_export.PUBLIC_DATA
            dashboard_export.PUBLIC_DATA = Path(directory)
            try:
                dashboard_export.write_json("meta.json", {"version": 1})
                dashboard_export.write_json("meta.json", {"version": 2})
            finally:
                dashboard_export.PUBLIC_DATA = original_public_data

            self.assertEqual(json.loads((Path(directory) / "meta.json").read_text()), {"version": 2})
            self.assertEqual(list(Path(directory).glob(".meta.json.*")), [])


if __name__ == "__main__":
    unittest.main()
