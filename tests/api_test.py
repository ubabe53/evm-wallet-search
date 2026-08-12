import os
import shutil
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import duckdb
from fastapi.testclient import TestClient

from scripts.artifact_paths import FIXTURE_DB_PATH
from server.app import create_app
from server.queries import DatabaseUnavailable, QueryService, json_value
from server.scan_jobs import ScanJobManager, resolve_wallet

FIXTURE_WALLET_ADDRESS = "0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"
FIXTURE_WALLET_LABEL = "Example wallet"


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

    def test_liveness_does_not_require_an_analytics_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.duckdb"
            client = TestClient(
                create_app(QueryService(missing), ScanJobManager(live_path=missing))
            )
            response = client.get("/api/v1/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_scan_job_and_wallet_list_contracts(self) -> None:
        manager = ScanJobManager(
            self.database_path,
            resolver=resolve_wallet,
            worker=lambda job, staging_path, progress: (_ for _ in ()).throw(RuntimeError("stub")),
            finalized_head=lambda: 42,
        )
        client = TestClient(create_app(self.service, manager))
        response = client.post("/api/v1/scan-jobs", json={"wallet": FIXTURE_WALLET_ADDRESS})
        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["from_block"], 0)
        self.assertEqual(payload["to_block"], 42)
        self.assertEqual(payload["wallet_address"], FIXTURE_WALLET_ADDRESS)
        self.assertEqual(client.get(f"/api/v1/scan-jobs/{payload['job_id']}").status_code, 200)
        self.assertEqual(client.get("/api/v1/wallets").status_code, 200)

    def test_active_scan_job_contract_is_process_local_and_nullable(self) -> None:
        started = threading.Event()
        release = threading.Event()

        def blocking_worker(job, staging_path, progress) -> None:
            started.set()
            release.wait(timeout=2)
            raise RuntimeError("test worker stopped")

        manager = ScanJobManager(
            self.database_path,
            resolver=resolve_wallet,
            worker=blocking_worker,
            finalized_head=lambda: 42,
        )
        client = TestClient(create_app(self.service, manager))

        self.assertEqual(client.get("/api/v1/scan-jobs/active").json(), {"job": None})
        response = client.post("/api/v1/scan-jobs", json={"wallet": FIXTURE_WALLET_ADDRESS})
        self.assertEqual(response.status_code, 202)

        try:
            self.assertTrue(started.wait(timeout=1))
            payload = client.get("/api/v1/scan-jobs/active").json()
            self.assertEqual(payload["job"]["job_id"], response.json()["job_id"])
            self.assertEqual(payload["job"]["status"], "running")
        finally:
            release.set()

    def test_scan_job_rejects_invalid_wallet(self) -> None:
        manager = ScanJobManager(self.database_path, resolver=resolve_wallet, finalized_head=lambda: 1)
        client = TestClient(create_app(self.service, manager))
        self.assertEqual(client.post("/api/v1/scan-jobs", json={"wallet": "not-an-address"}).status_code, 422)

    def test_token_recognition_override_table_has_exact_contract(self) -> None:
        with self.service.connect() as connection:
            actual = [
                (row[1], row[2], bool(row[3]), row[4], bool(row[5]))
                for row in connection.execute(
                    "pragma table_info('app.token_recognition_overrides')"
                ).fetchall()
            ]

        self.assertEqual(
            actual,
            [
                ("chain_id", "INTEGER", True, None, True),
                ("token_address", "VARCHAR", True, None, True),
                ("status", "VARCHAR", True, None, False),
                (
                    "updated_at",
                    "TIMESTAMP WITH TIME ZONE",
                    True,
                    "current_timestamp",
                    False,
                ),
            ],
        )

    def test_health_and_metadata_disclose_fixture_test_source(self) -> None:
        health = self.client.get("/api/v1/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(health.json()["data_source"], "fixture")

        metadata = self.client.get("/api/v1/metadata").json()
        selected_metadata = self.client.get(
            "/api/v1/metadata",
            params={"wallet_address": FIXTURE_WALLET_ADDRESS},
        ).json()
        self.assertEqual(selected_metadata["wallet_address"], metadata["wallet_address"])
        self.assertEqual(metadata["api_schema_version"], "dashboard-api-v16")
        self.assertEqual(
            set(metadata),
            {
                "configured_wallet_label",
                "wallet_address",
                "chain_id",
                "data_source",
                "generated_at",
                "snapshot_run_id",
                "snapshot_generation_id",
                "snapshot_start_block",
                "snapshot_end_block",
                "snapshot_end_block_hash",
                "snapshot_finality_policy",
                "snapshot_scope_version",
                "transfer_count",
                "event_block_number_min",
                "event_block_number_max",
                "first_event_at",
                "last_event_at",
                "account_evidence_population_scope",
                "account_evidence_eligible_address_count",
                "account_evidence_classified_address_count",
                "account_evidence_failed_address_count",
                "account_evidence_not_checked_address_count",
                "account_evidence_eligible_event_count",
                "account_evidence_classified_event_count",
                "account_evidence_failed_event_count",
                "account_evidence_not_checked_event_count",
                "account_evidence_observation_block_number_min",
                "account_evidence_observation_block_number_max",
                "account_evidence_observation_block_timestamp_min",
                "account_evidence_observation_block_timestamp_max",
                "account_evidence_schema_version",
                "api_schema_version",
                "database_mode",
                "completeness_scope",
                "indexer_checkpoint_recorded",
                "finality_status",
                "is_sampled",
            },
        )
        self.assertEqual(metadata["chain_id"], 1)
        self.assertEqual(metadata["configured_wallet_label"], FIXTURE_WALLET_LABEL)
        self.assertEqual(metadata["database_mode"], "fixture_test")
        self.assertFalse(metadata["is_sampled"])
        self.assertGreater(metadata["transfer_count"], 10)
        self.assertEqual(metadata["event_block_number_min"], 14000001)
        self.assertEqual(metadata["event_block_number_max"], 27000001)
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

    def test_active_wallet_is_derived_from_metadata_or_explicit_environment(self) -> None:
        wallet_address = FIXTURE_WALLET_ADDRESS
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(self.service.active_wallet_address(), wallet_address)
        with patch.dict(os.environ, {"EVM_WALLET_SCAN_ADDRESS": "0x" + wallet_address[2:].upper()}, clear=True):
            self.assertEqual(self.service.active_wallet_address(), wallet_address)

    def test_active_wallet_requires_selector_when_metadata_is_not_unique(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "multiple-wallets.duckdb"
            shutil.copy2(FIXTURE_DB_PATH, database_path)
            with duckdb.connect(str(database_path)) as connection:
                connection.execute("insert into pipeline_metadata select * from pipeline_metadata limit 1")
                connection.execute(
                    "update pipeline_metadata set wallet_address = ? where rowid = (select max(rowid) from pipeline_metadata)",
                    ["0x" + "b" * 40],
                )
            service = QueryService(database_path, require_live=False)
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(
                DatabaseUnavailable, "No active wallet selected; set EVM_WALLET_SCAN_ADDRESS"
            ):
                service.active_wallet_address()

    def test_completed_snapshot_run_exposes_finalized_contiguous_coverage(self) -> None:
        with TemporaryDirectory() as directory:
            database_path = Path(directory) / "live-test.duckdb"
            shutil.copy2(FIXTURE_DB_PATH, database_path)
            with duckdb.connect(str(database_path)) as connection:
                fixture_profile = connection.execute(
                    "select count(*), max(block_number) + 10 from wallet_events"
                ).fetchone()
                if fixture_profile is None:
                    raise AssertionError("fixture profile query returned no row")
                event_count, snapshot_end_block = fixture_profile
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
                      'run-1', 1, ?, ?, 0, ?, ?, ?, 'completed', current_timestamp,
                      'wallet-transfer-signature-v1'
                    )
                    """,
                    [
                        FIXTURE_WALLET_ADDRESS,
                        FIXTURE_WALLET_LABEL,
                        snapshot_end_block,
                        "0x" + "a" * 64,
                        event_count,
                    ],
                )
                connection.execute(
                    """
                    update pipeline_metadata set
                      data_source = 'hyperindex', snapshot_run_id = 'run-1',
                      snapshot_start_block = 0, snapshot_end_block = ?,
                      snapshot_end_block_hash = ?,
                      snapshot_finality_policy = 'ethereum_finalized',
                      snapshot_scope_version = 'wallet-transfer-signature-v1'
                    """,
                    [snapshot_end_block, "0x" + "a" * 64],
                )

            metadata = QueryService(database_path).metadata()
            self.assertTrue(metadata["indexer_checkpoint_recorded"])
            self.assertEqual(metadata["completeness_scope"], "finalized_block_range")
            self.assertEqual(metadata["finality_status"], "finalized")
            self.assertEqual(metadata["snapshot_start_block"], 0)
            self.assertEqual(metadata["snapshot_end_block"], snapshot_end_block)

            with duckdb.connect(str(database_path)) as connection:
                connection.execute(
                    "update ops.pipeline_runs set from_block = 1 where run_id = 'run-1'"
                )
            with self.assertRaisesRegex(DatabaseUnavailable, "non-contiguous"):
                QueryService(database_path).metadata()

            with duckdb.connect(str(database_path)) as connection:
                connection.execute(
                    "update ops.pipeline_runs set from_block = 0, events_found = ? "
                    "where run_id = 'run-1'",
                    [event_count - 1],
                )
            with self.assertRaisesRegex(DatabaseUnavailable, "do not reconcile"):
                QueryService(database_path).metadata()

    def test_decimal_serialization_preserves_values_beyond_ieee_754_precision(self) -> None:
        value = Decimal("12345678901234567890.123456789012345678")
        self.assertEqual(json_value(value), "12345678901234567890.123456789012345678")

    def test_event_response_is_the_lean_dashboard_contract(self) -> None:
        event_payload = self.client.get("/api/v1/events", params={"limit": 1}).json()
        event = event_payload["items"][0]
        self.assertEqual(
            event["transfer_id"],
            f"{event['chain_id']}-{event['transaction_hash']}-{event['log_index']}",
        )
        self.assertEqual(
            set(event),
            {
                "transfer_id",
                "chain_id",
                "wallet_address",
                "block_number",
                "block_timestamp",
                "transaction_hash",
                "transaction_index",
                "log_index",
                "token_address",
                "token_symbol",
                "token_name",
                "recognition_status",
                "direction",
                "is_indirect",
                "counterparty_address",
                "counterparty_account_type",
                "counterparty_code_state",
                "counterparty_observation_block_number",
                "counterparty_eip7702_delegation_target",
            },
        )

    def test_summary_uses_every_matching_row(self) -> None:
        default = self.client.get("/api/v1/summary").json()

        self.assertGreater(default["transfer_count"], 10)
        self.assertGreaterEqual(default["token_count"], 5)
        self.assertFalse(default["provenance"]["is_sampled"])

    def test_public_account_filters_are_binary_and_validated(self) -> None:
        response = self.client.get(
            "/api/v1/summary",
            params=[("account", "eoa_candidate"), ("account", "contract")],
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["transfer_count"],
            self.client.get("/api/v1/summary").json()["transfer_count"],
        )

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
        self.assertGreater(recognized.json()["transfer_count"], 0)
        self.assertGreater(other.json()["transfer_count"], 0)
        self.assertEqual(
            recognized.json()["transfer_count"] + other.json()["transfer_count"],
            self.client.get("/api/v1/summary").json()["transfer_count"],
        )
        self.assertEqual(other.json()["query"]["recognition"], "other")
        self.assertEqual(
            self.client.get("/api/v1/summary", params={"recognition": "invalid"}).status_code,
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
                json={"status": "invalid"},
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

    def test_timeline_buckets_reconcile_to_exact_date_filtered_queries(self) -> None:
        yearly_timeline = self.client.get(
            "/api/v1/timeline",
            params={"interval": "year"},
        )
        self.assertEqual(yearly_timeline.status_code, 200, yearly_timeline.text)
        yearly_payload = yearly_timeline.json()
        self.assertEqual(yearly_payload["interval"], "year")
        self.assertIsNone(yearly_payload["year"])
        self.assertEqual(
            yearly_payload["complete_matching_count"],
            self.client.get("/api/v1/summary").json()["transfer_count"],
        )

        selected_year = next(
            item for item in yearly_payload["items"] if item["self_transfer_count"] > 0
        )["bucket_start"][:4]
        timeline = self.client.get(
            "/api/v1/timeline",
            params={"interval": "month", "year": selected_year},
        )
        self.assertEqual(timeline.status_code, 200, timeline.text)
        payload = timeline.json()
        self.assertEqual(payload["interval"], "month")
        self.assertEqual(payload["year"], int(selected_year))
        self.assertEqual(payload["returned_count"], 12)
        self.assertGreater(payload["complete_matching_count"], 0)
        self.assertEqual(
            sum(item["transfer_count"] for item in payload["items"]),
            payload["complete_matching_count"],
        )
        self.assertTrue(all(
            item["transfer_count"]
            == (
                item["inbound_transfer_count"]
                + item["outbound_transfer_count"]
                + item["self_transfer_count"]
            )
            for item in payload["items"]
        ))
        self.assertEqual(sum(item["self_transfer_count"] for item in payload["items"]), 1)

        selected = next(item for item in payload["items"] if item["transfer_count"] > 0)
        period = {"start": selected["bucket_start"], "end": selected["bucket_end"]}
        summary = self.client.get("/api/v1/summary", params=period).json()
        counterparties = self.client.get(
            "/api/v1/counterparties",
            params={**period, "limit": 100},
        ).json()
        events = self.client.get(
            "/api/v1/events",
            params={**period, "limit": 100},
        ).json()

        self.assertEqual(summary["transfer_count"], selected["transfer_count"])
        self.assertEqual(events["complete_matching_count"], selected["transfer_count"])
        self.assertEqual(
            summary["counterparty_count"],
            counterparties["complete_matching_count"],
        )
        self.assertEqual(summary["query"]["start_at"], f"{selected['bucket_start']}T00:00:00+00:00")
        self.assertEqual(summary["query"]["end_before"], f"{selected['bucket_end']}T00:00:00+00:00")

    def test_timeline_interval_and_half_open_date_range_are_validated(self) -> None:
        self.assertEqual(
            self.client.get("/api/v1/timeline", params={"interval": "quarter"}).status_code,
            422,
        )
        self.assertEqual(
            self.client.get("/api/v1/timeline", params={"interval": "month"}).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/timeline",
                params={"interval": "year", "year": 2023},
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.get("/api/v1/summary", params={"start": "2023-11-14"}).status_code,
            422,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/summary",
                params={"start": "2023-11-15", "end": "2023-11-15"},
            ).status_code,
            422,
        )

    def test_timeline_applies_recognition_before_bucketing(self) -> None:
        recognized = self.client.get(
            "/api/v1/timeline",
            params={"recognition": "recognized", "interval": "year"},
        ).json()
        other = self.client.get(
            "/api/v1/timeline",
            params={"recognition": "other", "interval": "year"},
        ).json()

        self.assertEqual(
            recognized["complete_matching_count"],
            self.client.get(
                "/api/v1/summary", params={"recognition": "recognized"}
            ).json()["transfer_count"],
        )
        self.assertEqual(
            other["complete_matching_count"],
            self.client.get(
                "/api/v1/summary", params={"recognition": "other"}
            ).json()["transfer_count"],
        )
        self.assertEqual(recognized["returned_count"], other["returned_count"])
        self.assertEqual(other["query"]["recognition"], "other")

    def test_event_cursor_pages_complete_results_without_sampling(self) -> None:
        first = self.client.get(
            "/api/v1/events", params={"limit": 2}
        ).json()
        second = self.client.get(
            "/api/v1/events",
            params={"limit": 2, "cursor": first["next_cursor"]},
        ).json()

        self.assertGreater(first["complete_matching_count"], first["returned_count"])
        self.assertEqual(first["returned_count"], 2)
        self.assertTrue(first["is_paginated"])
        self.assertFalse(first["is_sampled"])
        self.assertTrue({item["transfer_id"] for item in first["items"]}.isdisjoint(
            {item["transfer_id"] for item in second["items"]}
        ))
        self.assertIsNotNone(second["next_cursor"])
        self.assertEqual(self.client.get("/api/v1/events", params={"cursor": "broken"}).status_code, 400)

    def test_self_transfer_is_neither_directional_nor_a_counterparty(self) -> None:
        with self.service.connect() as connection:
            self_event_row = connection.execute(
                """
                select transaction_hash
                from wallet_events
                where direction = 'self'
                order by block_number, transaction_index, log_index
                limit 1
                """
            ).fetchone()
        self.assertIsNotNone(self_event_row)
        assert self_event_row is not None
        transaction_hash = self_event_row[0]
        event = self.client.get(
            "/api/v1/events",
            params={"q": transaction_hash, "limit": 1},
        ).json()["items"][0]
        token = self.client.get(
            "/api/v1/tokens",
            params={"q": transaction_hash, "limit": 1},
        ).json()["items"][0]
        summary = self.client.get(
            "/api/v1/summary",
            params={"q": transaction_hash},
        ).json()

        self.assertEqual(event["direction"], "self")
        self.assertEqual(event["counterparty_address"], event["wallet_address"])
        self.assertEqual(token["self_transfer_count"], 1)
        self.assertEqual(
            token["transfer_count"],
            token["inbound_transfer_count"]
            + token["outbound_transfer_count"]
            + token["self_transfer_count"],
        )
        self.assertEqual(summary["transfer_count"], 1)
        self.assertEqual(summary["counterparty_count"], 0)

    def test_ranked_endpoints_disclose_complete_and_returned_counts(self) -> None:
        for endpoint in ("tokens", "counterparties"):
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

    def test_counterparty_ranking_uses_inclusive_recognition_cohort(self) -> None:
        inserted_transaction_hash = "0x" + "f" * 64
        with self.service.connect() as connection:
            recognized_counterparty_row = connection.execute(
                """
                select counterparty_address
                from wallet_events
                where recognition_status = 'recognized'
                  and counterparty_address != wallet_address
                  and counterparty_address != '0x0000000000000000000000000000000000000000'
                order by block_number, transaction_index, log_index
                limit 1
                """
            ).fetchone()
            self.assertIsNotNone(recognized_counterparty_row)
            assert recognized_counterparty_row is not None
            mixed_address = recognized_counterparty_row[0]
            existing_count = connection.execute(
                "select count(*) from wallet_events where counterparty_address = ?",
                [mixed_address],
            ).fetchone()[0]
            connection.execute(
                """
                insert into wallet_events
                select * replace (
                  17000010 as block_number,
                  ? as transaction_hash,
                  10 as transaction_index,
                  10 as log_index,
                  ? as counterparty_address,
                  'other' as recognition_status
                )
                from wallet_events
                where recognition_status = 'other'
                limit 1
                """,
                [inserted_transaction_hash, mixed_address],
            )

        try:
            for recognition in ("recognized", "other"):
                with self.subTest(recognition=recognition):
                    parameters = {
                        "recognition": recognition,
                        "q": mixed_address,
                        "limit": 10,
                    }
                    counterparties = self.client.get(
                        "/api/v1/counterparties", params=parameters
                    ).json()
                    self.assertEqual(counterparties["items"][0]["counterparty_address"], mixed_address)
                    self.assertEqual(counterparties["items"][0]["transfer_count"], existing_count + 1)
        finally:
            with self.service.connect() as connection:
                connection.execute(
                    "delete from wallet_events where transaction_hash = ?",
                    [inserted_transaction_hash],
                )

    def test_live_api_rejects_a_fixture_database(self) -> None:
        client = TestClient(create_app(QueryService(FIXTURE_DB_PATH)))
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 503)
        self.assertIn("requires a HyperIndex-built live database", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
