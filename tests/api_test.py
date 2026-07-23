import shutil
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb
from fastapi.testclient import TestClient

from scripts.artifact_paths import FIXTURE_DB_PATH
from server.app import create_app
from server.queries import DatabaseUnavailable, QueryService, json_value


class DashboardApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE_DB_PATH.exists():
            raise RuntimeError("Run bun run analytics:build:fixture before API tests")
        cls.temporary_directory = TemporaryDirectory()
        cls.database_path = Path(cls.temporary_directory.name) / "api-test.duckdb"
        shutil.copy2(FIXTURE_DB_PATH, cls.database_path)
        cls.service = QueryService(cls.database_path, require_live=False)
        cls.client = TestClient(create_app(cls.service))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary_directory.cleanup()

    def setUp(self) -> None:
        with self.service.connect() as connection:
            connection.execute("delete from app.token_recognition_overrides")

    def test_health_and_metadata_disclose_fixture_test_source(self) -> None:
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["data_source"], "fixture")

        metadata = self.client.get("/api/v1/metadata").json()
        self.assertEqual(metadata["api_schema_version"], "dashboard-api-v8")
        self.assertEqual(metadata["database_mode"], "fixture_test")
        self.assertFalse(metadata["is_sampled"])
        self.assertEqual(metadata["transfer_count"], 6)
        self.assertEqual(metadata["event_block_number_min"], 17000001)
        self.assertEqual(metadata["completeness_scope"], "duckdb_snapshot")
        self.assertFalse(metadata["indexer_checkpoint_recorded"])
        self.assertEqual(metadata["finality_status"], "not_recorded")
        self.assertIsNone(metadata["snapshot_start_block"])
        self.assertIsNone(metadata["snapshot_end_block"])
        self.assertEqual(
            metadata["account_evidence_population_scope"],
            "distinct_nonzero_nonself_event_counterparties",
        )
        self.assertEqual(
            metadata["account_evidence_eligible_address_count"],
            metadata["account_evidence_classified_address_count"]
            + metadata["account_evidence_failed_address_count"]
            + metadata["account_evidence_not_checked_address_count"],
        )
        self.assertEqual(
            metadata["account_evidence_eligible_event_count"],
            metadata["account_evidence_classified_event_count"]
            + metadata["account_evidence_failed_event_count"]
            + metadata["account_evidence_not_checked_event_count"],
        )

    def test_completed_snapshot_run_exposes_finalized_contiguous_coverage(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "live-test.duckdb"
            shutil.copy2(FIXTURE_DB_PATH, database_path)
            with duckdb.connect(str(database_path)) as connection:
                connection.execute("create schema ops")
                connection.execute(
                    """
                    create table ops.pipeline_runs (
                      run_id varchar, chain_id integer, wallet_address varchar, wallet_label varchar,
                      from_block bigint, to_block bigint, to_block_hash varchar, events_found bigint,
                      status varchar, completed_at timestamptz, scope_version varchar
                    )
                    """
                )
                connection.execute(
                    """
                    insert into ops.pipeline_runs values (
                      'run-1', 1, '0xd8da6bf26964af9d7eed9e03e53415d37aa96045',
                      'vitalik.eth', 0, 17000010, ?, 6, 'completed', current_timestamp,
                      'wallet-transfer-signature-v1'
                    )
                    """,
                    ["0x" + "a" * 64],
                )
                connection.execute(
                    """
                    update pipeline_metadata set
                      data_source = 'hyperindex', snapshot_run_id = 'run-1',
                      snapshot_start_block = 0, snapshot_increment_start_block = 0,
                      snapshot_end_block = 17000010, snapshot_end_block_hash = ?,
                      snapshot_finality_policy = 'ethereum_finalized',
                      snapshot_scope_version = 'wallet-transfer-signature-v1'
                    """,
                    ["0x" + "a" * 64],
                )

            metadata = QueryService(database_path).metadata()
            self.assertTrue(metadata["indexer_checkpoint_recorded"])
            self.assertEqual(metadata["completeness_scope"], "finalized_block_range")
            self.assertEqual(metadata["finality_status"], "finalized")
            self.assertEqual(metadata["snapshot_start_block"], 0)
            self.assertEqual(metadata["snapshot_end_block"], 17000010)

            with duckdb.connect(str(database_path)) as connection:
                connection.execute(
                    "update ops.pipeline_runs set from_block = 1 where run_id = 'run-1'"
                )
            with self.assertRaisesRegex(DatabaseUnavailable, "non-contiguous"):
                QueryService(database_path).metadata()

    def test_decimal_serialization_preserves_values_beyond_ieee_754_precision(self) -> None:
        value = Decimal("12345678901234567890.123456789012345678")
        self.assertEqual(json_value(value), "12345678901234567890.123456789012345678")

    def test_raw_uint256_value_is_exact_in_event_and_token_responses(self) -> None:
        expected = (
            "115792089237316195423570985008687907853269984665640564039457"
            "584007913129639935"
        )
        event_payload = self.client.get(
            "/api/v1/events",
            params={"q": "0xeee", "limit": 1},
        ).json()
        token_payload = self.client.get(
            "/api/v1/tokens",
            params={"q": "0x9999999999999999999999999999999999999999", "limit": 1},
        ).json()

        self.assertEqual(event_payload["items"][0]["value_raw"], expected)
        self.assertNotIn("amount_decimal", event_payload["items"][0])
        self.assertEqual(token_payload["items"][0]["value_raw_sum"], expected)
        self.assertNotIn("amount_decimal_sum", token_payload["items"][0])

    def test_summary_uses_every_matching_row(self) -> None:
        default = self.client.get("/api/v1/summary").json()

        self.assertEqual(default["transfer_count"], 6)
        self.assertEqual(default["token_count"], 5)
        self.assertFalse(default["provenance"]["is_sampled"])

    def test_public_account_filters_are_binary_and_validated(self) -> None:
        response = self.client.get(
            "/api/v1/summary",
            params=[("account", "eoa_candidate"), ("account", "contract")],
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["transfer_count"], 6)

        invalid = self.client.get("/api/v1/summary", params={"account": "human"})
        self.assertEqual(invalid.status_code, 422)
        internal = self.client.get("/api/v1/summary", params={"account": "unknown"})
        self.assertEqual(internal.status_code, 422)

        empty = self.client.get("/api/v1/summary", params={"account": "none"})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["transfer_count"], 0)

        mixed_none = self.client.get(
            "/api/v1/summary",
            params=[("account", "none"), ("account", "contract")],
        )
        self.assertEqual(mixed_none.status_code, 422)

    def test_recognition_filter_uses_exact_automatic_classification(self) -> None:
        recognized = self.client.get(
            "/api/v1/summary",
            params={"recognition": "recognized"},
        )
        other = self.client.get(
            "/api/v1/summary",
            params={"recognition": "other"},
        )

        self.assertEqual(recognized.status_code, 200)
        self.assertEqual(recognized.json()["transfer_count"], 5)
        self.assertEqual(other.json()["transfer_count"], 1)
        self.assertEqual(other.json()["query"]["recognition"], "other")
        self.assertEqual(
            self.client.get("/api/v1/summary", params={"recognition": "trusted"}).status_code,
            422,
        )

    def test_token_recognition_override_is_persistent_and_resettable(self) -> None:
        token_address = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
        changed = self.client.put(
            f"/api/v1/tokens/{token_address}/recognition",
            json={"status": "other"},
        )

        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["automatic_status"], "recognized")
        self.assertEqual(changed.json()["recognition_status"], "other")
        self.assertEqual(changed.json()["recognition_source"], "manual")
        self.assertIsNone(changed.json()["previous_override_status"])

        filtered = self.client.get(
            "/api/v1/tokens",
            params={"recognition": "other", "limit": 100},
        ).json()
        overridden = next(item for item in filtered["items"] if item["token_address"] == token_address)
        self.assertEqual(overridden["recognition_status"], "other")
        self.assertEqual(overridden["recognition_source"], "manual")
        self.assertEqual(overridden["recognition_override_status"], "other")

        reopened = QueryService(self.database_path, require_live=False)
        self.assertEqual(reopened.token_recognition(token_address)["override_status"], "other")

        reset = self.client.delete(f"/api/v1/tokens/{token_address}/recognition")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.json()["recognition_status"], "recognized")
        self.assertEqual(reset.json()["recognition_source"], "automatic")
        self.assertEqual(reset.json()["previous_override_status"], "other")

    def test_token_recognition_override_validates_address_token_and_status(self) -> None:
        self.assertEqual(
            self.client.put("/api/v1/tokens/not-an-address/recognition", json={"status": "other"}).status_code,
            422,
        )
        self.assertEqual(
            self.client.put(
                "/api/v1/tokens/0x1111111111111111111111111111111111111111/recognition",
                json={"status": "other"},
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.put(
                "/api/v1/tokens/0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48/recognition",
                json={"status": "trusted"},
            ).status_code,
            422,
        )

    def test_search_runs_before_exact_counts(self) -> None:
        event = self.client.get(
            "/api/v1/events", params={"limit": 1}
        ).json()["items"][0]
        result = self.client.get(
            "/api/v1/summary",
            params={"q": event["transaction_hash"]},
        ).json()
        self.assertEqual(result["transfer_count"], 1)
        self.assertEqual(result["token_count"], 1)

    def test_event_cursor_pages_complete_results_without_sampling(self) -> None:
        first = self.client.get(
            "/api/v1/events", params={"limit": 2}
        ).json()
        second = self.client.get(
            "/api/v1/events",
            params={"limit": 2, "cursor": first["next_cursor"]},
        ).json()

        self.assertEqual(first["complete_matching_count"], 6)
        self.assertEqual(first["returned_count"], 2)
        self.assertTrue(first["is_paginated"])
        self.assertFalse(first["is_sampled"])
        self.assertTrue({item["transfer_id"] for item in first["items"]}.isdisjoint(
            {item["transfer_id"] for item in second["items"]}
        ))
        self.assertIsNotNone(second["next_cursor"])
        self.assertEqual(self.client.get("/api/v1/events", params={"cursor": "broken"}).status_code, 400)

    def test_ranked_endpoints_disclose_complete_and_returned_counts(self) -> None:
        for endpoint in ("tokens", "counterparties", "graph"):
            with self.subTest(endpoint=endpoint):
                response = self.client.get(
                    f"/api/v1/{endpoint}",
                    params={"limit": 1},
                )
                self.assertEqual(response.status_code, 200, response.text)
                payload = response.json()
                self.assertEqual(payload["returned_count"], 1)
                self.assertGreaterEqual(payload["complete_matching_count"], payload["returned_count"])
                self.assertEqual(
                    payload["is_truncated"],
                    payload["complete_matching_count"] > payload["returned_count"],
                )
                self.assertFalse(payload["is_sampled"])

    def test_counterparty_and_graph_rank_the_same_inclusive_recognition_cohort(self) -> None:
        mixed_address = "0x1111111111111111111111111111111111111111"
        inserted_transfer_id = "fixture-mixed-recognition"
        with self.service.connect() as connection:
            connection.execute(
                """
                insert into wallet_events
                select * replace (
                  ? as transfer_id,
                  17000010 as block_number,
                  ? as transaction_hash,
                  10 as transaction_index,
                  10 as log_index,
                  ? as from_address,
                  ? as counterparty_address,
                  'other' as recognition_status,
                  'no_registry_match' as recognition_reason,
                  'automatic' as recognition_source
                )
                from wallet_events
                where recognition_status = 'other'
                limit 1
                """,
                [inserted_transfer_id, "0x" + "f" * 64, mixed_address, mixed_address],
            )

        try:
            for recognition in ("recognized", "other"):
                with self.subTest(recognition=recognition):
                    parameters = {"recognition": recognition, "limit": 10}
                    counterparties = self.client.get(
                        "/api/v1/counterparties", params=parameters
                    ).json()
                    graph = self.client.get("/api/v1/graph", params=parameters).json()

                    self.assertEqual(counterparties["items"][0]["counterparty_address"], mixed_address)
                    self.assertEqual(counterparties["items"][0]["transfer_count"], 2)
                    self.assertEqual(graph["items"][0]["counterparty_address"], mixed_address)
                    self.assertEqual(graph["items"][0]["transfer_count"], 2)
                    self.assertEqual(
                        [item["counterparty_address"] for item in graph["items"]],
                        [item["counterparty_address"] for item in counterparties["items"]],
                    )
                    self.assertNotIn("token_address", graph["items"][0])
                    self.assertNotIn("direction", graph["items"][0])
        finally:
            with self.service.connect() as connection:
                connection.execute("delete from wallet_events where transfer_id = ?", [inserted_transfer_id])

    def test_live_api_rejects_a_fixture_database(self) -> None:
        client = TestClient(create_app(QueryService(FIXTURE_DB_PATH)))
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 503)
        self.assertIn("requires a HyperIndex-built live database", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
