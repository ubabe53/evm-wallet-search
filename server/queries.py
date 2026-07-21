"""Exact, bounded DuckDB queries for the local dashboard API."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

import duckdb


ACCOUNT_FILTERS = (
    "eoa_candidate",
    "eip7702_delegated",
    "safe",
    "erc4337_account",
    "contract",
    "unknown",
)
SPAM_STATUSES = ("suspected_spam", "spam")
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
API_SCHEMA_VERSION = "dashboard-api-v1"


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured analytics artifact cannot serve requests."""


class InvalidCursor(ValueError):
    """Raised when an event cursor is malformed."""


@dataclass(frozen=True)
class DashboardFilters:
    include_spam: bool = False
    account_filters: tuple[str, ...] = ACCOUNT_FILTERS
    query: str | None = None


def json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def rows(connection: Any, sql: str, parameters: Iterable[Any] = ()) -> list[dict[str, Any]]:
    result = connection.execute(sql, list(parameters))
    columns = [column[0] for column in result.description]
    return [
        {column: json_value(value) for column, value in zip(columns, row)}
        for row in result.fetchall()
    ]


def filter_sql(filters: DashboardFilters) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    parameters: list[Any] = []
    if not filters.include_spam:
        clauses.append("events.token_status not in (?, ?)")
        parameters.extend(SPAM_STATUSES)

    selected = tuple(dict.fromkeys(filters.account_filters))
    if not selected:
        clauses.append("false")
    elif set(selected) != set(ACCOUNT_FILTERS):
        account_clauses: list[str] = []
        primary = [value for value in selected if value not in {"safe", "erc4337_account"}]
        if primary:
            placeholders = ", ".join("?" for _ in primary)
            account_clauses.append(f"events.counterparty_account_type in ({placeholders})")
            parameters.extend(primary)
        if "safe" in selected:
            account_clauses.append("events.counterparty_is_safe")
        if "erc4337_account" in selected:
            account_clauses.append("events.counterparty_is_erc4337_account")
        clauses.append(f"({' or '.join(account_clauses)})")

    if filters.query:
        clauses.append(
            "contains(lower(concat_ws('|', "
            "events.transfer_id, events.transaction_hash, events.transaction_from_address, "
            "events.transaction_to_address, cast(events.block_date as varchar), events.direction, "
            "events.transaction_sender_relation, events.transaction_target_relation, events.ens, "
            "events.wallet_address, events.from_address, events.to_address, events.counterparty_address, "
            "events.counterparty_account_type, events.counterparty_code_state, "
            "events.counterparty_safe_version, events.counterparty_erc4337_entrypoint_version, "
            "events.counterparty_evidence_reason_codes, events.token_address, events.token_symbol, "
            "events.token_name, events.metadata_availability, events.metadata_source)), ?)"
        )
        parameters.append(filters.query.strip().lower())

    return " and ".join(clauses) if clauses else "true", parameters


def filtered_cte(filters: DashboardFilters) -> tuple[str, list[Any]]:
    predicate, parameters = filter_sql(filters)
    return f"with filtered_events as (select * from wallet_events as events where {predicate})", parameters


def encode_cursor(row: dict[str, Any]) -> str:
    payload = [row["block_number"], row["transaction_index"], row["log_index"], row["transfer_id"]]
    return base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[int, int, int, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if (
            not isinstance(payload, list)
            or len(payload) != 4
            or not all(isinstance(value, int) for value in payload[:3])
            or not isinstance(payload[3], str)
        ):
            raise ValueError
        return payload[0], payload[1], payload[2], payload[3]
    except (ValueError, TypeError, binascii.Error, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise InvalidCursor("Invalid event cursor") from error


class QueryService:
    def __init__(self, database_path: Path, *, require_live: bool = True) -> None:
        self.database_path = database_path
        self.require_live = require_live

    def connect(self) -> Any:
        if not self.database_path.is_file():
            raise DatabaseUnavailable(
                "Live analytics are unavailable; run bun run analytics:build:hyperindex first"
            )
        connection = None
        try:
            connection = duckdb.connect(str(self.database_path), read_only=True)
            metadata = rows(connection, "select * from pipeline_metadata order by wallet_id")
        except Exception as error:
            if connection is not None:
                connection.close()
            raise DatabaseUnavailable("The analytics database could not be opened") from error
        if len(metadata) != 1:
            connection.close()
            raise DatabaseUnavailable("The analytics database must contain one configured wallet")
        if self.require_live and metadata[0]["data_source"] != "hyperindex":
            connection.close()
            raise DatabaseUnavailable("The local API requires a HyperIndex-built live database")
        return connection

    def metadata(self) -> dict[str, Any]:
        with self.connect() as connection:
            metadata = rows(connection, "select * from pipeline_metadata")[0]
            block_bounds = rows(
                connection,
                "select min(block_number) as event_block_number_min, max(block_number) as event_block_number_max from wallet_events",
            )[0]
        return {
            **metadata,
            **block_bounds,
            "api_schema_version": API_SCHEMA_VERSION,
            "database_mode": "live" if metadata["data_source"] == "hyperindex" else "fixture_test",
            "completeness_scope": "duckdb_snapshot",
            "indexer_checkpoint_recorded": False,
            "finality_status": "not_recorded",
            "is_sampled": False,
        }

    def provenance(self, connection: Any) -> dict[str, Any]:
        metadata = rows(
            connection,
            """
            select metadata.wallet_id, metadata.ens, metadata.wallet_address, metadata.chain_id,
              metadata.data_source, metadata.generated_at,
              first_event_at, last_event_at, account_evidence_observation_block_number_min,
              account_evidence_observation_block_number_max,
              account_evidence_observation_block_timestamp_min,
              account_evidence_observation_block_timestamp_max,
              account_evidence_coverage_scope, account_evidence_coverage_start_block,
              account_evidence_coverage_end_block, account_evidence_schema_version,
              min(events.block_number) as event_block_number_min,
              max(events.block_number) as event_block_number_max
            from pipeline_metadata as metadata
            left join wallet_events as events using (wallet_id)
            group by all
            """,
        )[0]
        return {
            **metadata,
            "api_schema_version": API_SCHEMA_VERSION,
            "completeness_scope": "duckdb_snapshot",
            "indexer_checkpoint_recorded": False,
            "finality_status": "not_recorded",
            "is_sampled": False,
        }

    @staticmethod
    def query_contract(filters: DashboardFilters) -> dict[str, Any]:
        return {
            "include_spam": filters.include_spam,
            "account_evidence": list(filters.account_filters),
            "query": filters.query,
        }

    def summary(self, filters: DashboardFilters) -> dict[str, Any]:
        cte, parameters = filtered_cte(filters)
        with self.connect() as connection:
            result = rows(
                connection,
                f"""
                {cte}
                select count(*) as transfer_count,
                  count(distinct token_address) as token_count,
                  count(distinct counterparty_address) as counterparty_count,
                  min(block_number) as block_number_min,
                  max(block_number) as block_number_max,
                  min(block_timestamp) as first_event_at,
                  max(block_timestamp) as last_event_at
                from filtered_events
                """,
                parameters,
            )[0]
            provenance = self.provenance(connection)
        return {"provenance": provenance, "query": self.query_contract(filters), **result}

    def events(
        self,
        filters: DashboardFilters,
        *,
        limit: int,
        cursor: str | None,
    ) -> dict[str, Any]:
        cte, parameters = filtered_cte(filters)
        count_parameters = list(parameters)
        cursor_sql = ""
        if cursor:
            block_number, transaction_index, log_index, transfer_id = decode_cursor(cursor)
            cursor_sql = """
              where block_number < ?
                 or (block_number = ? and transaction_index < ?)
                 or (block_number = ? and transaction_index = ? and log_index < ?)
                 or (block_number = ? and transaction_index = ? and log_index = ? and transfer_id < ?)
            """
            parameters.extend([
                block_number,
                block_number, transaction_index,
                block_number, transaction_index, log_index,
                block_number, transaction_index, log_index, transfer_id,
            ])
        with self.connect() as connection:
            total = rows(connection, f"{cte} select count(*) as count from filtered_events", count_parameters)[0]["count"]
            items = rows(
                connection,
                f"""
                {cte}
                select * from filtered_events
                {cursor_sql}
                order by block_number desc, transaction_index desc, log_index desc, transfer_id desc
                limit {limit + 1}
                """,
                parameters,
            )
            provenance = self.provenance(connection)
        has_more = len(items) > limit
        returned = items[:limit]
        return {
            "provenance": provenance,
            "query": self.query_contract(filters),
            "complete_matching_count": total,
            "returned_count": len(returned),
            "limit": limit,
            "next_cursor": encode_cursor(returned[-1]) if has_more and returned else None,
            "is_paginated": total > len(returned),
            "is_sampled": False,
            "items": returned,
        }

    def tokens(self, filters: DashboardFilters, *, limit: int) -> dict[str, Any]:
        cte, parameters = filtered_cte(filters)
        with self.connect() as connection:
            total = rows(connection, f"{cte} select count(distinct token_address) as count from filtered_events", parameters)[0]["count"]
            items = rows(
                connection,
                f"""
                {cte}
                select
                  any_value(wallet_id) as wallet_id,
                  any_value(wallet_address) as wallet_address,
                  token_address,
                  coalesce(any_value(token_symbol), substr(token_address, 1, 10)) as token_symbol,
                  any_value(token_name) as token_name,
                  any_value(token_decimals) as token_decimals,
                  any_value(token_status) as token_status,
                  any_value(metadata_source) as metadata_source,
                  any_value(metadata_source_url) as metadata_source_url,
                  any_value(metadata_availability) as metadata_availability,
                  count(*) as transfer_count,
                  count(*) filter (where direction = 'in') as inbound_transfer_count,
                  count(*) filter (where direction = 'out') as outbound_transfer_count,
                  count(*) filter (where direction = 'in' and is_indirect) as indirect_inbound_transfer_count,
                  count(*) filter (where direction = 'out' and is_indirect) as indirect_outbound_transfer_count,
                  count(distinct counterparty_address) filter (
                    where counterparty_address != '{ZERO_ADDRESS}' and counterparty_address != wallet_address
                  ) as counterparty_count,
                  count(distinct counterparty_address) filter (
                    where direction = 'in' and counterparty_address != '{ZERO_ADDRESS}' and counterparty_address != wallet_address
                  ) as sender_account_count,
                  count(distinct counterparty_address) filter (
                    where direction = 'out' and counterparty_address != '{ZERO_ADDRESS}' and counterparty_address != wallet_address
                  ) as recipient_account_count,
                  case when count(amount_decimal) = count(*) then sum(amount_decimal) else null end as amount_decimal_sum,
                  cast(sum(cast(value_raw as bignum)) as varchar) as value_raw_sum
                from filtered_events
                group by token_address
                order by transfer_count desc, token_address
                limit {limit}
                """,
                parameters,
            )
            provenance = self.provenance(connection)
        return {
            "provenance": provenance,
            "query": self.query_contract(filters),
            "complete_matching_count": total,
            "returned_count": len(items),
            "limit": limit,
            "is_truncated": total > len(items),
            "is_sampled": False,
            "items": items,
        }

    def counterparties(self, filters: DashboardFilters, *, limit: int) -> dict[str, Any]:
        cte, parameters = filtered_cte(filters)
        eligible = f"""
          select events.* from filtered_events as events
          where events.counterparty_address != '{ZERO_ADDRESS}'
            and events.counterparty_address != events.wallet_address
            and not exists (
              select 1 from wallet_events as token_events
              where token_events.token_address = events.counterparty_address
            )
        """
        with self.connect() as connection:
            total = rows(connection, f"{cte} select count(distinct counterparty_address) as count from ({eligible})", parameters)[0]["count"]
            items = rows(
                connection,
                f"""
                {cte}
                select
                  any_value(wallet_id) as wallet_id,
                  any_value(wallet_address) as wallet_address,
                  any_value(chain_id) as chain_id,
                  counterparty_address,
                  any_value(counterparty_account_type) as account_type,
                  any_value(counterparty_code_state) as code_state,
                  any_value(counterparty_code_size_bytes) as code_size_bytes,
                  any_value(counterparty_observation_block_number) as observation_block_number,
                  any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
                  any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
                  bool_or(counterparty_is_safe) as is_safe,
                  any_value(counterparty_safe_verification_status) as safe_verification_status,
                  any_value(counterparty_safe_version) as safe_version,
                  any_value(counterparty_safe_singleton_address) as safe_singleton_address,
                  any_value(counterparty_safe_owner_count) as safe_owner_count,
                  any_value(counterparty_safe_threshold) as safe_threshold,
                  bool_or(counterparty_is_erc4337_account) as is_erc4337_account,
                  any_value(counterparty_erc4337_user_operation_count) as erc4337_user_operation_count,
                  any_value(counterparty_erc4337_first_observed_block) as erc4337_first_observed_block,
                  any_value(counterparty_erc4337_last_observed_block) as erc4337_last_observed_block,
                  any_value(counterparty_erc4337_entrypoint_address) as erc4337_entrypoint_address,
                  any_value(counterparty_erc4337_entrypoint_version) as erc4337_entrypoint_version,
                  any_value(counterparty_erc4337_entrypoint_source) as erc4337_entrypoint_source,
                  any_value(counterparty_erc4337_entrypoint_deployment_block) as erc4337_entrypoint_deployment_block,
                  any_value(counterparty_erc4337_effective_coverage) as erc4337_effective_coverage,
                  any_value(counterparty_erc4337_failed_ranges) as erc4337_failed_ranges,
                  any_value(counterparty_evidence_fetch_status) as evidence_fetch_status,
                  any_value(counterparty_evidence_reason_codes) as evidence_reason_codes,
                  any_value(counterparty_evidence_coverage_scope) as evidence_coverage_scope,
                  any_value(counterparty_evidence_coverage_start_block) as evidence_coverage_start_block,
                  any_value(counterparty_evidence_coverage_end_block) as evidence_coverage_end_block,
                  any_value(counterparty_evidence_schema_version) as evidence_schema_version,
                  count(*) as transfer_count,
                  count(*) filter (where direction = 'in') as inbound_transfer_count,
                  count(*) filter (where direction = 'out') as outbound_transfer_count,
                  count(distinct token_address) as token_count,
                  min(block_timestamp) as first_seen_at,
                  max(block_timestamp) as last_seen_at
                from ({eligible})
                group by counterparty_address
                order by transfer_count desc, last_seen_at desc, counterparty_address
                limit {limit}
                """,
                parameters,
            )
            provenance = self.provenance(connection)
        return {
            "provenance": provenance,
            "query": self.query_contract(filters),
            "complete_matching_count": total,
            "returned_count": len(items),
            "limit": limit,
            "is_truncated": total > len(items),
            "is_sampled": False,
            "items": items,
        }

    def graph(self, filters: DashboardFilters, *, limit: int) -> dict[str, Any]:
        cte, parameters = filtered_cte(filters)
        interaction_sql = f"""
          select
            any_value(wallet_id) as wallet_id,
            any_value(ens) as ens,
            wallet_address,
            counterparty_address,
            token_address,
            coalesce(any_value(token_symbol), substr(token_address, 1, 10)) as token_symbol,
            any_value(token_status) as token_status,
            direction,
            any_value(counterparty_account_type) as account_type,
            bool_or(counterparty_is_safe) as is_safe,
            bool_or(counterparty_is_erc4337_account) as is_erc4337_account,
            any_value(counterparty_observation_block_number) as observation_block_number,
            any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
            any_value(counterparty_safe_version) as safe_version,
            any_value(counterparty_safe_owner_count) as safe_owner_count,
            any_value(counterparty_safe_threshold) as safe_threshold,
            any_value(counterparty_erc4337_entrypoint_version) as erc4337_entrypoint_version,
            any_value(counterparty_erc4337_effective_coverage) as erc4337_effective_coverage,
            any_value(counterparty_erc4337_failed_ranges) as erc4337_failed_ranges,
            any_value(counterparty_evidence_coverage_start_block) as evidence_coverage_start_block,
            any_value(counterparty_evidence_coverage_end_block) as evidence_coverage_end_block,
            count(*) as transfer_count,
            max(block_timestamp) as last_seen_at
          from filtered_events
          where counterparty_address != '{ZERO_ADDRESS}'
          group by wallet_address, counterparty_address, token_address, direction
        """
        with self.connect() as connection:
            total = rows(connection, f"{cte} select count(*) as count from ({interaction_sql})", parameters)[0]["count"]
            items = rows(
                connection,
                f"""
                {cte}, counterparty_activity as (
                  select wallet_address, counterparty_address, count(*) as counterparty_transfer_count
                  from wallet_events
                  group by wallet_address, counterparty_address
                )
                select interactions.*, activity.counterparty_transfer_count
                from ({interaction_sql}) as interactions
                join counterparty_activity as activity using (wallet_address, counterparty_address)
                order by interactions.transfer_count desc, interactions.last_seen_at desc,
                  interactions.counterparty_address, interactions.token_address, interactions.direction
                limit {limit}
                """,
                parameters,
            )
            provenance = self.provenance(connection)
        return {
            "provenance": provenance,
            "query": self.query_contract(filters),
            "complete_matching_count": total,
            "returned_count": len(items),
            "limit": limit,
            "is_truncated": total > len(items),
            "is_sampled": False,
            "items": items,
        }
