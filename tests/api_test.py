import unittest
from decimal import Decimal

from fastapi.testclient import TestClient

from scripts.artifact_paths import FIXTURE_DB_PATH
from server.app import create_app
from server.queries import QueryService, json_value


class DashboardApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE_DB_PATH.exists():
            raise RuntimeError("Run bun run analytics:build:fixture before API tests")
        cls.client = TestClient(create_app(QueryService(FIXTURE_DB_PATH, require_live=False)))

    def test_health_and_metadata_disclose_fixture_test_source(self) -> None:
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["data_source"], "fixture")

        metadata = self.client.get("/api/v1/metadata").json()
        self.assertEqual(metadata["api_schema_version"], "dashboard-api-v2")
        self.assertEqual(metadata["database_mode"], "fixture_test")
        self.assertFalse(metadata["is_sampled"])
        self.assertEqual(metadata["transfer_count"], 6)
        self.assertEqual(metadata["event_block_number_min"], 17000001)
        self.assertEqual(metadata["completeness_scope"], "duckdb_snapshot")
        self.assertFalse(metadata["indexer_checkpoint_recorded"])
        self.assertEqual(metadata["finality_status"], "not_recorded")

    def test_decimal_serialization_preserves_values_beyond_ieee_754_precision(self) -> None:
        value = Decimal("12345678901234567890.123456789012345678")
        self.assertEqual(json_value(value), "12345678901234567890.123456789012345678")

    def test_summary_uses_every_matching_row(self) -> None:
        default = self.client.get("/api/v1/summary").json()
        with_spam = self.client.get("/api/v1/summary", params={"include_spam": "true"}).json()

        self.assertEqual(default["transfer_count"], 5)
        self.assertEqual(with_spam["transfer_count"], 6)
        self.assertEqual(with_spam["token_count"], 5)
        self.assertFalse(with_spam["provenance"]["is_sampled"])

    def test_public_account_filters_are_binary_and_validated(self) -> None:
        response = self.client.get(
            "/api/v1/summary",
            params=[("include_spam", "true"), ("account", "eoa_candidate"), ("account", "contract")],
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

    def test_search_runs_before_exact_counts(self) -> None:
        event = self.client.get(
            "/api/v1/events", params={"include_spam": "true", "limit": 1}
        ).json()["items"][0]
        result = self.client.get(
            "/api/v1/summary",
            params={"include_spam": "true", "q": event["transaction_hash"]},
        ).json()
        self.assertEqual(result["transfer_count"], 1)
        self.assertEqual(result["token_count"], 1)

    def test_event_cursor_pages_complete_results_without_sampling(self) -> None:
        first = self.client.get(
            "/api/v1/events", params={"include_spam": "true", "limit": 2}
        ).json()
        second = self.client.get(
            "/api/v1/events",
            params={"include_spam": "true", "limit": 2, "cursor": first["next_cursor"]},
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
                    params={"include_spam": "true", "limit": 1},
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

    def test_live_api_rejects_a_fixture_database(self) -> None:
        client = TestClient(create_app(QueryService(FIXTURE_DB_PATH)))
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 503)
        self.assertIn("requires a HyperIndex-built live database", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
