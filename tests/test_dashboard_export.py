import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import scripts.export_dashboard as dashboard_export


class DashboardExportTest(unittest.TestCase):
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
