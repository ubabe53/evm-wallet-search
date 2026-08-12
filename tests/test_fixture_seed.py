import csv
import io
import re
import unittest
from datetime import datetime, timezone

from scripts.generate_fixture_events import (
    COUNTERPARTIES,
    FIXTURE_WALLET_ADDRESS,
    MAX_UINT256,
    SEED_PATH,
    TOKENS,
    ZERO_ADDRESS,
    render_fixture_csv,
)


class FixtureSeedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = list(csv.DictReader(io.StringIO(render_fixture_csv())))

    def test_checked_in_seed_is_reproducible(self) -> None:
        self.assertEqual(SEED_PATH.read_text(), render_fixture_csv())

    def test_public_fixture_has_exact_event_contract_and_synthetic_identity(self) -> None:
        self.assertEqual(len(self.rows), 100)
        self.assertEqual(
            len({(row["chain_id"], row["transaction_hash"], row["log_index"]) for row in self.rows}),
            100,
        )
        self.assertRegex(FIXTURE_WALLET_ADDRESS, r"^0x[0-9a-f]{40}$")
        self.assertNotEqual(FIXTURE_WALLET_ADDRESS, ZERO_ADDRESS)
        self.assertNotIn(FIXTURE_WALLET_ADDRESS, {address for address, _ in TOKENS})
        self.assertNotIn(FIXTURE_WALLET_ADDRESS, COUNTERPARTIES)
        self.assertTrue(all(row["chain_id"] == "1" for row in self.rows))
        self.assertTrue(all(re.fullmatch(r"0x[0-9a-f]{64}", row["block_hash"]) for row in self.rows))
        self.assertTrue(all(re.fullmatch(r"0x[0-9a-f]{64}", row["transaction_hash"]) for row in self.rows))
        self.assertTrue(all(row["value_raw"].isdigit() for row in self.rows))
        self.assertIn(str(MAX_UINT256), {row["value_raw"] for row in self.rows})
        self.assertTrue(all(
            row["from_address"] == FIXTURE_WALLET_ADDRESS
            or row["to_address"] == FIXTURE_WALLET_ADDRESS
            for row in self.rows
        ))

    def test_public_fixture_is_ordered_and_exercises_dashboard_scenarios(self) -> None:
        block_numbers = [int(row["block_number"]) for row in self.rows]
        timestamps = [int(row["block_timestamp"]) for row in self.rows]
        self.assertEqual(block_numbers, sorted(block_numbers))
        self.assertEqual(timestamps, sorted(timestamps))

        event_times = [datetime.fromtimestamp(timestamp, timezone.utc) for timestamp in timestamps]
        self.assertEqual({event_time.year for event_time in event_times}, set(range(2022, 2027)))
        self.assertGreaterEqual(len({(event_time.year, event_time.month) for event_time in event_times}), 40)
        self.assertLessEqual(max(event_times), datetime(2026, 7, 31, tzinfo=timezone.utc))
        self.assertEqual({row["token_address"] for row in self.rows}, {address for address, _ in TOKENS})
        self.assertEqual(
            {row["from_address"] for row in self.rows} | {row["to_address"] for row in self.rows},
            {FIXTURE_WALLET_ADDRESS, ZERO_ADDRESS, *COUNTERPARTIES},
        )

        directions = {
            "self" if row["from_address"] == row["to_address"] == FIXTURE_WALLET_ADDRESS
            else "in" if row["to_address"] == FIXTURE_WALLET_ADDRESS
            else "out"
            for row in self.rows
        }
        directness = {
            "unknown" if not row["transaction_from_address"]
            else "direct" if row["transaction_from_address"] == row["from_address"]
            else "indirect"
            for row in self.rows
        }
        self.assertEqual(directions, {"in", "out", "self"})
        self.assertEqual(directness, {"direct", "indirect", "unknown"})
        self.assertTrue(any(row["from_address"] == ZERO_ADDRESS for row in self.rows))
        self.assertTrue(any(row["to_address"] == ZERO_ADDRESS for row in self.rows))


if __name__ == "__main__":
    unittest.main()
