"""Exact, bounded DuckDB queries for the local dashboard API."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

import duckdb

ACCOUNT_FILTERS = (
    "eoa_candidate",
    "contract",
)
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")
API_SCHEMA_VERSION = "dashboard-api-v13"


class DatabaseUnavailable(RuntimeError):
    """Raised when the configured analytics artifact cannot serve requests."""


class InvalidCursor(ValueError):
    """Raised when an event cursor is malformed."""


class InvalidTokenAddress(ValueError):
    """Raised when a token override address is not a canonical EVM address."""


class TokenNotFound(LookupError):
    """Raised when an override targets a token absent from the analytics snapshot."""


@dataclass(frozen=True)
class DashboardFilters:
    account_filters: tuple[str, ...] = ACCOUNT_FILTERS
    query: str | None = None
    recognition: str = "all"
    start_at: datetime | None = None
    end_before: datetime | None = None


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
        {column: json_value(value) for column, value in zip(columns, row, strict=True)}
        for row in result.fetchall()
    ]


def filter_sql(
    filters: DashboardFilters,
    *,
    include_recognition: bool = True,
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    parameters: list[Any] = []
    if include_recognition and filters.recognition != "all":
        clauses.append("events.recognition_status = ?")
        parameters.append(filters.recognition)

    selected = tuple(dict.fromkeys(filters.account_filters))
    if not selected:
        clauses.append("false")
    elif set(selected) != set(ACCOUNT_FILTERS):
        placeholders = ", ".join("?" for _ in selected)
        clauses.append(f"events.counterparty_account_type in ({placeholders})")
        parameters.extend(selected)

    if filters.query:
        clauses.append(
            "contains(lower(concat_ws('|', "
            "events.transfer_id, events.transaction_hash, events.transaction_from_address, "
            "events.transaction_to_address, cast(events.block_date as varchar), events.direction, "
            "events.transaction_sender_relation, events.transaction_target_relation, "
            "(select metadata.ens from pipeline_metadata as metadata "
            "where metadata.chain_id = events.chain_id "
            "and metadata.wallet_address = events.wallet_address), "
            "events.wallet_address, events.from_address, events.to_address, events.counterparty_address, "
            "events.counterparty_account_type, events.counterparty_code_state, "
            "events.counterparty_evidence_reason_codes, events.token_address, events.token_symbol, "
            "events.token_name, events.recognition_status, events.recognition_source, "
            "events.metadata_availability, events.metadata_source)), ?)"
        )
        parameters.append(filters.query.strip().lower())

    if filters.start_at is not None:
        clauses.append("events.block_timestamp >= ?")
        parameters.append(filters.start_at)
    if filters.end_before is not None:
        clauses.append("events.block_timestamp < ?")
        parameters.append(filters.end_before)

    return " and ".join(clauses) if clauses else "true", parameters


def filtered_cte(filters: DashboardFilters) -> tuple[str, list[Any]]:
    predicate, parameters = filter_sql(filters)
    return f"""
      with effective_events as (
        select
          events.* exclude (recognition_status, recognition_reason, recognition_source),
          coalesce(overrides.status, events.recognition_status) as recognition_status,
          case
            when overrides.status is not null then 'manual_override'
            else events.recognition_reason
          end as recognition_reason,
          case
            when overrides.status is not null then 'manual'
            else events.recognition_source
          end as recognition_source,
          overrides.status as recognition_override_status
        from wallet_events as events
        left join app.token_recognition_overrides as overrides
          on overrides.chain_id = events.chain_id
          and overrides.token_address = events.token_address
      ),
      filtered_events as (select * from effective_events as events where {predicate})
    """, parameters


def counterparty_cte(filters: DashboardFilters) -> tuple[str, list[Any]]:
    """Select a counterparty cohort without discarding its opposite-recognition activity.

    Recognition decides whether an address belongs in the cohort. Once eligible, all
    events within the remaining account/search scope contribute to its displayed
    activity, so an address that used both recognized and other tokens remains intact.
    """
    predicate, parameters = filter_sql(filters, include_recognition=False)
    recognition_predicate = "true"
    if filters.recognition != "all":
        recognition_predicate = "events.recognition_status = ?"
        parameters.append(filters.recognition)

    return f"""
      with effective_events as (
        select
          events.* exclude (recognition_status, recognition_reason, recognition_source),
          coalesce(overrides.status, events.recognition_status) as recognition_status,
          case
            when overrides.status is not null then 'manual_override'
            else events.recognition_reason
          end as recognition_reason,
          case
            when overrides.status is not null then 'manual'
            else events.recognition_source
          end as recognition_source,
          overrides.status as recognition_override_status
        from wallet_events as events
        left join app.token_recognition_overrides as overrides
          on overrides.chain_id = events.chain_id
          and overrides.token_address = events.token_address
      ),
      scoped_events as (
        select * from effective_events as events where {predicate}
      ),
      eligible_counterparties as (
        select distinct chain_id, wallet_address, counterparty_address
        from scoped_events as events
        where {recognition_predicate}
      ),
      counterparty_events as (
        select events.*
        from scoped_events as events
        join eligible_counterparties using (chain_id, wallet_address, counterparty_address)
      )
    """, parameters


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
        self._schema_ready = False
        self._schema_lock = Lock()

    def connect(self) -> Any:
        if not self.database_path.is_file():
            raise DatabaseUnavailable(
                "Live analytics are unavailable; run bun run analytics:build:hyperindex first"
            )
        connection = None
        try:
            connection = duckdb.connect(str(self.database_path), read_only=False)
            metadata = rows(
                connection,
                "select * from pipeline_metadata order by chain_id, wallet_address",
            )
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
        snapshot_run_id = metadata[0].get("snapshot_run_id")
        if metadata[0]["data_source"] == "hyperindex" and not snapshot_run_id:
            connection.close()
            raise DatabaseUnavailable(
                "The live analytics database has no verified finalized snapshot run"
            )
        if metadata[0]["data_source"] == "hyperindex":
            if metadata[0].get("snapshot_finality_policy") != "ethereum_finalized":
                connection.close()
                raise DatabaseUnavailable("The live analytics snapshot is not finalized")
            try:
                completed_runs = rows(
                    connection,
                    """
                    select run_id, from_block, to_block, to_block_hash
                    from ops.pipeline_runs
                    where chain_id = ?
                      and wallet_address = ?
                      and scope_version = ?
                      and status = 'completed'
                      and events_found is not null
                      and completed_at is not null
                    order by from_block, to_block
                    """,
                    [
                        metadata[0]["chain_id"],
                        metadata[0]["wallet_address"],
                        metadata[0]["snapshot_scope_version"],
                    ],
                )
            except Exception as error:
                connection.close()
                raise DatabaseUnavailable("The finalized snapshot run could not be verified") from error
            expected_start = metadata[0].get("snapshot_start_block")
            contiguous = isinstance(expected_start, int) and bool(completed_runs)
            for run in completed_runs:
                contiguous = contiguous and run["from_block"] == expected_start
                expected_start = run["to_block"] + 1
            latest_run = completed_runs[-1] if completed_runs else {}
            snapshot_end = metadata[0].get("snapshot_end_block")
            latest_matches = (
                isinstance(snapshot_end, int)
                and latest_run.get("run_id") == snapshot_run_id
                and latest_run.get("from_block")
                == metadata[0].get("snapshot_increment_start_block")
                and latest_run.get("to_block") == snapshot_end
                and latest_run.get("to_block_hash")
                == metadata[0].get("snapshot_end_block_hash")
                and expected_start == snapshot_end + 1
            )
            if not contiguous or not latest_matches:
                connection.close()
                raise DatabaseUnavailable(
                    "The finalized snapshot runs are incomplete or non-contiguous"
                )
        with self._schema_lock:
            if not self._schema_ready:
                connection.execute("create schema if not exists app")
                connection.execute(
                    """
                    create table if not exists app.token_recognition_overrides (
                      chain_id integer not null check (chain_id = 1),
                      token_address varchar not null,
                      status varchar not null check (status in ('recognized', 'other')),
                      updated_at timestamptz not null default current_timestamp,
                      primary key (chain_id, token_address)
                    )
                    """
                )
                self._schema_ready = True
        return connection

    def metadata(self) -> dict[str, Any]:
        with self.connect() as connection:
            metadata = rows(connection, "select * from pipeline_metadata")[0]
            block_bounds = rows(
                connection,
                "select min(block_number) as event_block_number_min, max(block_number) as event_block_number_max from wallet_events",
            )[0]
        checkpoint_recorded = metadata.get("snapshot_run_id") is not None
        return {
            **metadata,
            **block_bounds,
            "api_schema_version": API_SCHEMA_VERSION,
            "database_mode": "live" if metadata["data_source"] == "hyperindex" else "fixture_test",
            "completeness_scope": "finalized_block_range" if checkpoint_recorded else "duckdb_snapshot",
            "indexer_checkpoint_recorded": checkpoint_recorded,
            "finality_status": "finalized" if checkpoint_recorded else "not_recorded",
            "is_sampled": False,
        }

    def provenance(self, connection: Any) -> dict[str, Any]:
        metadata = rows(
            connection,
            """
            select metadata.ens, metadata.wallet_address, metadata.chain_id,
              metadata.data_source, metadata.generated_at,
              metadata.snapshot_run_id, metadata.snapshot_start_block,
              metadata.snapshot_increment_start_block, metadata.snapshot_end_block,
              metadata.snapshot_end_block_hash, metadata.snapshot_finality_policy,
              metadata.snapshot_scope_version,
              first_event_at, last_event_at,
              account_evidence_population_scope,
              account_evidence_eligible_address_count,
              account_evidence_classified_address_count,
              account_evidence_failed_address_count,
              account_evidence_not_checked_address_count,
              account_evidence_address_coverage_rate,
              account_evidence_eligible_event_count,
              account_evidence_classified_event_count,
              account_evidence_failed_event_count,
              account_evidence_not_checked_event_count,
              account_evidence_event_coverage_rate,
              account_evidence_observation_block_number_min,
              account_evidence_observation_block_number_max,
              account_evidence_observation_block_timestamp_min,
              account_evidence_observation_block_timestamp_max,
              account_evidence_schema_version,
              min(events.block_number) as event_block_number_min,
              max(events.block_number) as event_block_number_max
            from pipeline_metadata as metadata
            left join wallet_events as events using (chain_id, wallet_address)
            group by all
            """,
        )[0]
        checkpoint_recorded = metadata.get("snapshot_run_id") is not None
        return {
            **metadata,
            "api_schema_version": API_SCHEMA_VERSION,
            "completeness_scope": "finalized_block_range" if checkpoint_recorded else "duckdb_snapshot",
            "indexer_checkpoint_recorded": checkpoint_recorded,
            "finality_status": "finalized" if checkpoint_recorded else "not_recorded",
            "is_sampled": False,
        }

    @staticmethod
    def query_contract(filters: DashboardFilters) -> dict[str, Any]:
        return {
            "recognition": filters.recognition,
            "account_evidence": list(filters.account_filters),
            "query": filters.query,
            "start_at": filters.start_at.isoformat() if filters.start_at else None,
            "end_before": filters.end_before.isoformat() if filters.end_before else None,
        }

    @staticmethod
    def normalized_token_address(token_address: str) -> str:
        if not ADDRESS_PATTERN.fullmatch(token_address):
            raise InvalidTokenAddress("Token address must be a 20-byte hexadecimal address")
        return token_address.lower()

    def token_recognition(self, token_address: str) -> dict[str, Any]:
        address = self.normalized_token_address(token_address)
        with self.connect() as connection:
            result = rows(
                connection,
                """
                select
                  events.chain_id,
                  events.token_address,
                  any_value(events.token_symbol) as token_symbol,
                  any_value(events.recognition_status) as automatic_status,
                  any_value(events.recognition_reason) as automatic_reason,
                  overrides.status as override_status,
                  overrides.updated_at,
                  coalesce(overrides.status, any_value(events.recognition_status)) as recognition_status,
                  case when overrides.status is null then 'automatic' else 'manual' end as recognition_source
                from wallet_events as events
                left join app.token_recognition_overrides as overrides
                  on overrides.chain_id = events.chain_id
                  and overrides.token_address = events.token_address
                where events.chain_id = 1 and events.token_address = ?
                group by events.chain_id, events.token_address, overrides.status, overrides.updated_at
                """,
                [address],
            )
        if not result:
            raise TokenNotFound("Token is not present in the current analytics snapshot")
        return result[0]

    def set_token_recognition(self, token_address: str, status: str) -> dict[str, Any]:
        if status not in {"recognized", "other"}:
            raise ValueError("Recognition status must be recognized or other")
        address = self.normalized_token_address(token_address)
        previous = self.token_recognition(address)
        with self.connect() as connection:
            connection.execute(
                """
                insert into app.token_recognition_overrides (chain_id, token_address, status, updated_at)
                values (1, ?, ?, current_timestamp)
                on conflict (chain_id, token_address) do update
                set status = excluded.status, updated_at = excluded.updated_at
                """,
                [address, status],
            )
        current = self.token_recognition(address)
        current["previous_override_status"] = previous["override_status"]
        return current

    def reset_token_recognition(self, token_address: str) -> dict[str, Any]:
        address = self.normalized_token_address(token_address)
        previous = self.token_recognition(address)
        with self.connect() as connection:
            connection.execute(
                "delete from app.token_recognition_overrides where chain_id = 1 and token_address = ?",
                [address],
            )
        current = self.token_recognition(address)
        current["previous_override_status"] = previous["override_status"]
        return current

    def summary(self, filters: DashboardFilters) -> dict[str, Any]:
        cte, parameters = filtered_cte(filters)
        with self.connect() as connection:
            result = rows(
                connection,
                f"""
                {cte}
                select count(*) as transfer_count,
                  count(distinct token_address) as token_count,
                  count(distinct counterparty_address) filter (
                    where counterparty_address != wallet_address
                  ) as counterparty_count,
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
                  any_value(chain_id) as chain_id,
                  any_value(wallet_address) as wallet_address,
                  token_address,
                  coalesce(any_value(token_symbol), substr(token_address, 1, 10)) as token_symbol,
                  any_value(token_name) as token_name,
                  any_value(token_decimals) as token_decimals,
                  any_value(recognition_status) as recognition_status,
                  any_value(recognition_reason) as recognition_reason,
                  any_value(recognition_source) as recognition_source,
                  any_value(recognition_version) as recognition_version,
                  any_value(recognition_override_status) as recognition_override_status,
                  any_value(metadata_source) as metadata_source,
                  any_value(metadata_source_url) as metadata_source_url,
                  any_value(metadata_availability) as metadata_availability,
                  count(*) as transfer_count,
                  count(*) filter (where direction = 'in') as inbound_transfer_count,
                  count(*) filter (where direction = 'out') as outbound_transfer_count,
                  count(*) filter (where direction = 'self') as self_transfer_count,
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
                  cast(sum(cast(value_raw as bignum)) as varchar) as value_raw_sum
                from filtered_events
                group by chain_id, wallet_address, token_address
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

    def timeline(
        self,
        filters: DashboardFilters,
        *,
        interval: str,
        year: int | None = None,
    ) -> dict[str, Any]:
        interval_steps = {
            "month": "interval '1 month'",
            "year": "interval '1 year'",
        }
        if interval not in interval_steps:
            raise ValueError("Timeline interval must be month or year")
        if interval == "month" and year is None:
            raise ValueError("Monthly timeline buckets require a year")
        if interval == "year" and year is not None:
            raise ValueError("Year is only valid for monthly timeline buckets")
        step = interval_steps[interval]
        cte, parameters = filtered_cte(filters)
        domain_parameters: list[Any] = []
        if interval == "year":
            domain_sql = """
              select
                date_trunc('year', min(timezone('UTC', block_timestamp))) as first_bucket,
                date_trunc('year', max(timezone('UTC', block_timestamp))) as last_bucket
              from wallet_events
            """
        else:
            domain_sql = """
              select
                cast(make_date(?, 1, 1) as timestamp) as first_bucket,
                case
                  when ? = year(max(timezone('UTC', block_timestamp)))
                    then date_trunc('month', max(timezone('UTC', block_timestamp)))
                  else cast(make_date(?, 12, 1) as timestamp)
                end as last_bucket
              from wallet_events
            """
            domain_parameters = [year, year, year]
        with self.connect() as connection:
            items = rows(
                connection,
                f"""
                {cte},
                bucket_counts as (
                  select
                    date_trunc('{interval}', timezone('UTC', block_timestamp)) as bucket_start,
                    count(*) as transfer_count,
                    count(*) filter (where direction = 'in') as inbound_transfer_count,
                    count(*) filter (where direction = 'out') as outbound_transfer_count,
                    count(*) filter (where direction = 'self') as self_transfer_count
                  from filtered_events
                  group by bucket_start
                ),
                bucket_bounds as (
                  {domain_sql}
                ),
                buckets as (
                  select bucket_start
                  from bucket_bounds,
                    unnest(generate_series(first_bucket, last_bucket, {step})) as generated(bucket_start)
                )
                select
                  cast(buckets.bucket_start as date) as bucket_start,
                  cast(buckets.bucket_start + {step} as date) as bucket_end,
                  coalesce(bucket_counts.transfer_count, 0) as transfer_count,
                  coalesce(bucket_counts.inbound_transfer_count, 0) as inbound_transfer_count,
                  coalesce(bucket_counts.outbound_transfer_count, 0) as outbound_transfer_count,
                  coalesce(bucket_counts.self_transfer_count, 0) as self_transfer_count
                from buckets
                left join bucket_counts using (bucket_start)
                order by buckets.bucket_start
                """,
                [*parameters, *domain_parameters],
            )
            provenance = self.provenance(connection)
        return {
            "provenance": provenance,
            "query": self.query_contract(filters),
            "interval": interval,
            "year": year,
            "complete_matching_count": sum(item["transfer_count"] for item in items),
            "returned_count": len(items),
            "is_sampled": False,
            "items": items,
        }

    def counterparties(self, filters: DashboardFilters, *, limit: int) -> dict[str, Any]:
        cte, parameters = counterparty_cte(filters)
        eligible = f"""
          select events.* from counterparty_events as events
          where events.counterparty_address != '{ZERO_ADDRESS}'
            and events.counterparty_address != events.wallet_address
            and not exists (
              select 1 from wallet_events as token_events
              where token_events.chain_id = events.chain_id
                and token_events.token_address = events.counterparty_address
            )
        """
        with self.connect() as connection:
            total = rows(connection, f"{cte} select count(distinct counterparty_address) as count from ({eligible})", parameters)[0]["count"]
            items = rows(
                connection,
                f"""
                {cte}
                select
                  chain_id,
                  wallet_address,
                  counterparty_address,
                  any_value(counterparty_account_type) as account_type,
                  any_value(counterparty_code_state) as code_state,
                  any_value(counterparty_code_size_bytes) as code_size_bytes,
                  any_value(counterparty_observation_block_number) as observation_block_number,
                  any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
                  any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
                  any_value(counterparty_evidence_fetch_status) as evidence_fetch_status,
                  any_value(counterparty_evidence_reason_codes) as evidence_reason_codes,
                  any_value(counterparty_evidence_schema_version) as evidence_schema_version,
                  count(*) as transfer_count,
                  count(*) filter (where direction = 'in') as inbound_transfer_count,
                  count(*) filter (where direction = 'out') as outbound_transfer_count,
                  count(distinct token_address) as token_count,
                  min(block_timestamp) as first_seen_at,
                  max(block_timestamp) as last_seen_at
                from ({eligible})
                group by chain_id, wallet_address, counterparty_address
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
        cte, parameters = counterparty_cte(filters)
        eligible = f"""
          select events.* from counterparty_events as events
          where events.counterparty_address != '{ZERO_ADDRESS}'
            and events.counterparty_address != events.wallet_address
            and not exists (
              select 1 from wallet_events as token_events
              where token_events.chain_id = events.chain_id
                and token_events.token_address = events.counterparty_address
            )
        """
        counterparty_sql = f"""
          select
            chain_id,
            wallet_address,
            counterparty_address,
            any_value(counterparty_account_type) as account_type,
            any_value(counterparty_code_state) as code_state,
            any_value(counterparty_code_size_bytes) as code_size_bytes,
            any_value(counterparty_observation_block_number) as observation_block_number,
            any_value(counterparty_observation_block_timestamp) as observation_block_timestamp,
            any_value(counterparty_eip7702_delegation_target) as eip7702_delegation_target,
            any_value(counterparty_evidence_fetch_status) as evidence_fetch_status,
            any_value(counterparty_evidence_reason_codes) as evidence_reason_codes,
            any_value(counterparty_evidence_schema_version) as evidence_schema_version,
            count(*) as transfer_count,
            count(*) filter (where direction = 'in') as inbound_transfer_count,
            count(*) filter (where direction = 'out') as outbound_transfer_count,
            count(distinct token_address) as token_count,
            min(block_timestamp) as first_seen_at,
            max(block_timestamp) as last_seen_at
          from ({eligible}) as events
          group by chain_id, wallet_address, counterparty_address
        """
        with self.connect() as connection:
            total = rows(
                connection,
                f"{cte} select count(*) as count from ({counterparty_sql})",
                parameters,
            )[0]["count"]
            items = rows(
                connection,
                f"""
                {cte}
                select * from ({counterparty_sql}) as counterparties
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
