import csv
import json
import re
import unittest
from pathlib import Path

from scripts.generate_mainnet_demo import (
    ATTRIBUTION_SOURCE_URL,
    SNAPSHOT_SCHEMA_VERSION,
    TRANSFER_SCOPE_VERSION,
    WALLET_ADDRESS,
    WALLET_LABEL,
    validate_snapshot_events,
)

SEED_DIR = Path(__file__).resolve().parents[1] / "analytics" / "seeds"


def read_csv(name: str) -> list[dict[str, str]]:
    with (SEED_DIR / name).open(newline="") as source:
        return list(csv.DictReader(source))


class MainnetDemoSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.events = read_csv("raw_transfer_events_demo.csv")
        cls.tokens = read_csv("token_rpc_metadata_demo.csv")
        cls.accounts = read_csv("account_evidence_demo.csv")
        cls.wallets = read_csv("wallets_demo.csv")
        cls.snapshot = read_csv("demo_snapshot.csv")
        cls.manifest = json.loads((SEED_DIR / "demo_snapshot_manifest.json").read_text())

    def test_snapshot_identity_and_finalized_provenance(self) -> None:
        self.assertEqual(self.wallets, [{"ens": WALLET_LABEL, "address": WALLET_ADDRESS}])
        self.assertEqual(len(self.snapshot), 1)
        snapshot = self.snapshot[0]
        self.assertEqual(snapshot["wallet_address"], WALLET_ADDRESS)
        self.assertEqual(snapshot["snapshot_start_block"], "0")
        self.assertEqual(snapshot["snapshot_finality_policy"], "ethereum_finalized")
        self.assertEqual(snapshot["snapshot_scope_version"], TRANSFER_SCOPE_VERSION)
        self.assertEqual(snapshot["snapshot_source"], "envio_hyperindex")
        self.assertEqual(snapshot["snapshot_schema_version"], SNAPSHOT_SCHEMA_VERSION)
        self.assertEqual(snapshot["wallet_attribution_source_url"], ATTRIBUTION_SOURCE_URL)
        self.assertRegex(snapshot["snapshot_end_block_hash"], r"^0x[0-9a-f]{64}$")

    def test_event_snapshot_is_complete_unsampled_and_canonically_shaped(self) -> None:
        self.assertEqual(len(self.events), 90)
        identities = {
            (row["chain_id"], row["transaction_hash"], row["log_index"])
            for row in self.events
        }
        self.assertEqual(len(identities), len(self.events))
        self.assertTrue(all(row["chain_id"] == "1" for row in self.events))
        self.assertTrue(all(
            row["from_address"] == WALLET_ADDRESS or row["to_address"] == WALLET_ADDRESS
            for row in self.events
        ))
        self.assertTrue(all(re.fullmatch(r"0x[0-9a-f]{64}", row["block_hash"]) for row in self.events))
        self.assertTrue(all(re.fullmatch(r"0x[0-9a-f]{64}", row["transaction_hash"]) for row in self.events))
        self.assertTrue(all(row["value_raw"].isdigit() for row in self.events))
        self.assertEqual([int(row["block_number"]) for row in self.events], sorted(
            int(row["block_number"]) for row in self.events
        ))
        self.assertEqual(self.manifest["event_count"], len(self.events))
        self.assertEqual(self.manifest["sampling"], "none")

    def test_every_demo_token_and_counterparty_has_pinned_enrichment(self) -> None:
        token_addresses = {row["token_address"] for row in self.events}
        self.assertEqual({row["token_address"] for row in self.tokens}, token_addresses)
        self.assertTrue(all(row["fetch_status"] == "complete" for row in self.tokens))
        self.assertEqual({row["rpc_block_number"] for row in self.tokens}, {
            str(self.manifest["enrichment_observation_block_number"])
        })

        counterparties = {
            row["to_address"] if row["from_address"] == WALLET_ADDRESS else row["from_address"]
            for row in self.events
        } - {WALLET_ADDRESS, "0x0000000000000000000000000000000000000000"}
        self.assertEqual({row["address"] for row in self.accounts}, counterparties)
        self.assertTrue(all(row["fetch_status"] == "complete" for row in self.accounts))
        self.assertEqual({row["account_type"] for row in self.accounts}, {"eoa_candidate", "contract"})
        self.assertEqual({row["observation_block_hash"] for row in self.accounts}, {
            self.manifest["enrichment_observation_block_hash"]
        })

    def test_snapshot_validation_rejects_count_and_interval_drift(self) -> None:
        snapshot = {
            "cumulative_event_count": 1,
            "snapshot_start_block": 0,
            "snapshot_end_block": 10,
        }
        validate_snapshot_events(snapshot, [{"block_number": 10}])

        with self.assertRaisesRegex(RuntimeError, "cumulative pipeline metadata"):
            validate_snapshot_events({**snapshot, "cumulative_event_count": 2}, [{"block_number": 10}])
        with self.assertRaisesRegex(RuntimeError, "outside the completed finalized interval"):
            validate_snapshot_events(snapshot, [{"block_number": 11}])

    def test_snapshot_validation_accepts_cumulative_rows_after_incremental_runs(self) -> None:
        validate_snapshot_events(
            {
                "cumulative_event_count": 2,
                "snapshot_start_block": 0,
                "snapshot_end_block": 20,
            },
            [{"block_number": 5}, {"block_number": 15}],
        )


if __name__ == "__main__":
    unittest.main()
