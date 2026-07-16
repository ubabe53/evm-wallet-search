import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import scripts.export_dashboard as dashboard_export


class DashboardExportTest(unittest.TestCase):
    def test_counterparty_candidates_cover_combined_status_rankings(self) -> None:
        duckdb = dashboard_export.ensure_duckdb()
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                """
                create table counterparty_summary (
                    counterparty_address varchar,
                    token_status varchar,
                    transfer_count integer,
                    last_seen_at timestamp
                )
                """
            )
            connection.executemany(
                "insert into counterparty_summary values (?, ?, ?, ?)",
                [
                    ("0xaaa", "trusted", 90, "2024-01-01"),
                    ("0xaaa", "unverified", 90, "2024-01-01"),
                    ("0xbbb", "trusted", 100, "2024-01-02"),
                    ("0xccc", "unverified", 100, "2024-01-02"),
                ],
            )

            exported = dashboard_export.counterparty_rows(
                connection,
                statuses=("trusted", "unverified"),
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
        self.assertEqual(max(combined_counts, key=combined_counts.get), "0xaaa")

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
