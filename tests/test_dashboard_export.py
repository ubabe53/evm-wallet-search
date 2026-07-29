import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import scripts.export_dashboard as dashboard_export


class DashboardExportTest(unittest.TestCase):
    def test_export_schema_requires_the_lean_dashboard_contract(self) -> None:
        duckdb = dashboard_export.ensure_duckdb()
        connection = duckdb.connect(":memory:")
        try:
            connection.execute(
                """
                create table pipeline_metadata (
                    configured_wallet_label varchar,
                    wallet_address varchar,
                    chain_id bigint,
                    data_source varchar,
                    generated_at timestamptz,
                    snapshot_run_id varchar,
                    snapshot_start_block bigint,
                    snapshot_end_block bigint,
                    snapshot_end_block_hash varchar,
                    snapshot_finality_policy varchar,
                    snapshot_scope_version varchar,
                    transfer_count bigint,
                    event_block_number_min bigint,
                    event_block_number_max bigint,
                    first_event_at timestamptz,
                    last_event_at timestamptz,
                    account_evidence_population_scope varchar,
                    account_evidence_eligible_address_count bigint,
                    account_evidence_classified_address_count bigint,
                    account_evidence_failed_address_count bigint,
                    account_evidence_not_checked_address_count bigint,
                    account_evidence_eligible_event_count bigint,
                    account_evidence_classified_event_count bigint,
                    account_evidence_failed_event_count bigint,
                    account_evidence_not_checked_event_count bigint,
                    account_evidence_observation_block_number_min bigint,
                    account_evidence_observation_block_number_max bigint,
                    account_evidence_observation_block_timestamp_min timestamptz,
                    account_evidence_observation_block_timestamp_max timestamptz,
                    account_evidence_schema_version varchar
                )
                """
            )
            connection.execute(
                """
                create table wallet_events (
                    chain_id bigint,
                    wallet_address varchar,
                    block_number bigint,
                    block_timestamp timestamp,
                    transaction_hash varchar,
                    transaction_index bigint,
                    log_index bigint,
                    token_address varchar,
                    token_symbol varchar,
                    token_name varchar,
                    recognition_status varchar,
                    direction varchar,
                    is_indirect boolean,
                    counterparty_address varchar,
                    counterparty_account_type varchar,
                    counterparty_code_state varchar,
                    counterparty_observation_block_number bigint
                )
                """
            )
            connection.execute(
                """
                create table token_summary (
                    indirect_inbound_transfer_count integer,
                    indirect_outbound_transfer_count integer,
                    self_transfer_count integer,
                    counterparty_account_type varchar
                )
                """
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "wallet_events is missing required export columns",
            ):
                dashboard_export.validate_export_schema(connection)

            connection.execute(
                "alter table wallet_events add column counterparty_eip7702_delegation_target varchar"
            )

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
                    chain_id bigint,
                    wallet_address varchar,
                    counterparty_address varchar,
                    account_type varchar,
                    code_state varchar,
                    observation_block_number bigint,
                    eip7702_delegation_target varchar,
                    recognition_status varchar,
                    transfer_count integer,
                    inbound_transfer_count integer,
                    outbound_transfer_count integer,
                    token_count integer,
                    first_seen_at timestamp,
                    last_seen_at timestamp
                )
                """
            )
            connection.executemany(
                """
                insert into counterparty_summary values (
                    1, '0xwallet', ?, 'contract', 'bytecode_present', 100, null,
                    ?, ?, ?, ?, 1, '2023-01-01', ?
                )
                """,
                [
                    ("0xaaa", "recognized", 90, 45, 45, "2024-01-01"),
                    ("0xaaa", "other", 90, 45, 45, "2024-01-01"),
                    ("0xbbb", "recognized", 100, 50, 50, "2024-01-02"),
                    ("0xccc", "other", 100, 50, 50, "2024-01-02"),
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
                    chain_id bigint,
                    wallet_address varchar,
                    counterparty_address varchar,
                    account_type varchar,
                    code_state varchar,
                    observation_block_number bigint,
                    eip7702_delegation_target varchar,
                    recognition_status varchar,
                    transfer_count integer,
                    inbound_transfer_count integer,
                    outbound_transfer_count integer,
                    token_count integer,
                    first_seen_at timestamp,
                    last_seen_at timestamp
                )
                """
            )
            connection.executemany(
                """
                insert into counterparty_summary values (
                    1, '0xwallet', ?, ?, 'not_checked', null, null,
                    ?, ?, ?, ?, 1, '2023-01-01', ?
                )
                """,
                [
                    ("0xunknown", "unknown", "recognized", 200, 100, 100, "2025-01-03"),
                    ("0xcontract", "contract", "recognized", 150, 75, 75, "2025-01-02"),
                    ("0xeoa", "eoa_candidate", "recognized", 125, 60, 65, "2025-01-01"),
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
                    chain_id bigint,
                    wallet_address varchar,
                    token_address varchar,
                    token_symbol varchar,
                    token_name varchar,
                    recognition_status varchar,
                    counterparty_account_type varchar,
                    transfer_count integer,
                    inbound_transfer_count integer,
                    outbound_transfer_count integer,
                    self_transfer_count integer,
                    indirect_inbound_transfer_count integer,
                    indirect_outbound_transfer_count integer,
                    counterparty_count integer,
                    sender_account_count integer,
                    recipient_account_count integer
                )
                """
            )
            connection.executemany(
                """
                insert into token_summary values (
                    1, '0xwallet', ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1, 1, 1
                )
                """,
                [
                    ("0xaaa", "A", "Token A", "recognized", "contract", 60, 30, 30),
                    ("0xaaa", "A", "Token A", "recognized", "eoa_candidate", 60, 30, 30),
                    ("0xbbb", "B", "Token B", "recognized", "contract", 100, 50, 50),
                    ("0xccc", "C", "Token C", "recognized", "eoa_candidate", 100, 50, 50),
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

    def test_sampling_covers_every_bounded_export(self) -> None:
        metadata = {
            "exported_event_count": 10,
            "complete_event_count": 10,
            "exported_token_summary_count": 6,
            "complete_token_summary_row_count": 6,
            "exported_counterparty_summary_count": 4,
            "complete_counterparty_summary_row_count": 4,
            "exported_timeline_row_count": 2,
            "complete_timeline_row_count": 2,
        }
        self.assertFalse(dashboard_export.export_is_sampled(metadata))

        for exported, complete in (
            ("exported_event_count", "complete_event_count"),
            ("exported_token_summary_count", "complete_token_summary_row_count"),
            ("exported_counterparty_summary_count", "complete_counterparty_summary_row_count"),
            ("exported_timeline_row_count", "complete_timeline_row_count"),
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
