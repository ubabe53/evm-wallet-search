#!/usr/bin/env python3
"""Export dbt-built DuckDB marts to static dashboard JSON.

GitHub Pages and other static hosts can serve these files directly; no database
or API server is required at dashboard runtime.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

try:
    from .artifact_paths import FIXTURE_DB_PATH
except ImportError:
    from artifact_paths import FIXTURE_DB_PATH


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = FIXTURE_DB_PATH
PUBLIC_DATA = ROOT / "public" / "data"

# Static JSON stays intentionally bounded; DuckDB remains the complete artifact.
EVENT_LIMIT_PER_RECOGNITION_ACCOUNT_EVIDENCE = 1_000
TOKEN_SUMMARY_RANKING_LIMIT_PER_RECOGNITION_ACCOUNT_SELECTION = 500
COUNTERPARTY_RANKING_LIMIT_PER_RECOGNITION_ACCOUNT_SELECTION = 50
TIMELINE_ROW_LIMIT_PER_RECOGNITION_ACCOUNT_EVIDENCE = 5_000
EXPORT_SCHEMA_VERSION = "dashboard-export-v1"
RECOGNITION_STATUSES = ("recognized", "other")
ACCOUNT_FILTERS = ("eoa_candidate", "contract")
REQUIRED_EXPORT_COLUMNS = {
    "pipeline_metadata": {
        "configured_wallet_label",
        "wallet_address",
        "chain_id",
        "data_source",
        "generated_at",
        "snapshot_run_id",
        "snapshot_start_block",
        "snapshot_end_block",
        "snapshot_end_block_hash",
        "snapshot_finality_policy",
        "snapshot_scope_version",
        "snapshot_source",
        "snapshot_schema_version",
        "wallet_attribution_source_url",
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
    },
    "wallet_events": {
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
    "token_summary": {
        "chain_id",
        "wallet_address",
        "token_address",
        "token_symbol",
        "token_name",
        "recognition_status",
        "counterparty_account_type",
        "transfer_count",
        "inbound_transfer_count",
        "outbound_transfer_count",
        "self_transfer_count",
        "indirect_inbound_transfer_count",
        "indirect_outbound_transfer_count",
        "counterparty_count",
        "sender_account_count",
        "recipient_account_count",
    },
    "counterparty_summary": {
        "chain_id",
        "wallet_address",
        "counterparty_address",
        "account_type",
        "code_state",
        "observation_block_number",
        "eip7702_delegation_target",
        "recognition_status",
        "transfer_count",
        "inbound_transfer_count",
        "outbound_transfer_count",
        "token_count",
        "first_seen_at",
        "last_seen_at",
    },
    "timeline_daily": {
        "chain_id",
        "wallet_address",
        "block_date",
        "token_address",
        "token_symbol",
        "recognition_status",
        "counterparty_account_type",
        "direction",
        "transfer_count",
    },
}


def ensure_duckdb() -> Any:
    try:
        import duckdb  # type: ignore

        return duckdb
    except ImportError:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(ROOT / "analytics" / "requirements.txt")],
            check=True,
        )
        import duckdb  # type: ignore

        return duckdb


def json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def query_rows(connection: Any, query: str, parameters: Sequence[Any] | None = None) -> list[dict[str, Any]]:
    result = connection.execute(query, parameters or [])
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def validate_export_schema(connection: Any) -> None:
    """Fail before writing files when required dashboard evidence is unavailable."""

    for table, required_columns in REQUIRED_EXPORT_COLUMNS.items():
        result = connection.execute(f"select * from {table} limit 0")
        available_columns = {column[0] for column in result.description}
        missing_columns = sorted(required_columns - available_columns)
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise RuntimeError(f"{table} is missing required export columns: {missing}")


def write_json(name: str, payload: Any) -> None:
    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    path = PUBLIC_DATA / name
    serialized = json.dumps(payload, default=json_default, indent=2) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(dir=PUBLIC_DATA, prefix=f".{name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as output:
            output.write(serialized)
            output.flush()
            os.fsync(output.fileno())
        temporary_path.replace(path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise


def export_is_sampled(metadata: dict[str, Any]) -> bool:
    """Return whether any browser-facing export is smaller than its complete mart."""

    count_pairs = (
        ("exported_event_count", "complete_event_count"),
        ("exported_token_summary_count", "complete_token_summary_row_count"),
        ("exported_counterparty_summary_count", "complete_counterparty_summary_row_count"),
        ("exported_timeline_row_count", "complete_timeline_row_count"),
    )
    return any(metadata[exported] < metadata[complete] for exported, complete in count_pairs)


def non_empty_subsets(values: tuple[str, ...]) -> list[tuple[str, ...]]:
    return [
        tuple(value for index, value in enumerate(values) if mask & (1 << index))
        for mask in range(1, 1 << len(values))
    ]


def token_summary_rows(
    connection: Any,
    recognition_statuses: tuple[str, ...] = RECOGNITION_STATUSES,
    account_filters: tuple[str, ...] = ACCOUNT_FILTERS,
    ranking_limit: int = TOKEN_SUMMARY_RANKING_LIMIT_PER_RECOGNITION_ACCOUNT_SELECTION,
) -> list[dict[str, Any]]:
    """Export per-cell rows for the exact token top-N union of every filter selection."""

    recognition_case = "case " + " ".join(
        f"when recognition_status = '{value}' then {1 << index}"
        for index, value in enumerate(recognition_statuses)
    ) + " else 0 end"
    account_bits = " + ".join(
        f"case when counterparty_account_type = '{value}' then {1 << index} else 0 end"
        for index, value in enumerate(account_filters)
    )
    candidates = query_rows(
        connection,
        f"""
          with classified as (
            select
              *,
              {recognition_case} as recognition_bit,
              {account_bits} as account_bits
            from token_summary
          ),
          selections as (
            select recognition_mask, account_mask
            from range(1, {1 << len(recognition_statuses)}) as recognition(recognition_mask)
            cross join range(1, {1 << len(account_filters)}) as accounts(account_mask)
          ),
          ranked as (
            select
              selections.recognition_mask,
              selections.account_mask,
              classified.token_address,
              sum(classified.transfer_count) as selected_transfer_count
            from selections
            inner join classified
              on (classified.recognition_bit & selections.recognition_mask) != 0
              and (
                (classified.account_bits & selections.account_mask) != 0
                or selections.account_mask = {(1 << len(account_filters)) - 1}
              )
            group by
              selections.recognition_mask,
              selections.account_mask,
              classified.token_address
            qualify row_number() over (
              partition by selections.recognition_mask, selections.account_mask
              order by selected_transfer_count desc, classified.token_address
            ) <= {ranking_limit}
          )
          select distinct token_address
          from ranked
        """,
    )
    candidate_addresses = {row["token_address"] for row in candidates}
    if not candidate_addresses:
        return []

    ordered_addresses = sorted(candidate_addresses)
    placeholders = ", ".join("?" for _ in ordered_addresses)
    return query_rows(
        connection,
        f"""
          select
            chain_id,
            wallet_address,
            token_address,
            token_symbol,
            token_name,
            recognition_status,
            counterparty_account_type,
            transfer_count,
            inbound_transfer_count,
            outbound_transfer_count,
            self_transfer_count,
            indirect_inbound_transfer_count,
            indirect_outbound_transfer_count,
            counterparty_count,
            sender_account_count,
            recipient_account_count
          from token_summary
          where token_address in ({placeholders})
          order by transfer_count desc, token_symbol, token_address, counterparty_account_type
        """,
        ordered_addresses,
    )


def counterparty_rows(
    connection: Any,
    recognition_statuses: tuple[str, ...] = RECOGNITION_STATUSES,
    account_filters: tuple[str, ...] = ACCOUNT_FILTERS,
    ranking_limit: int = COUNTERPARTY_RANKING_LIMIT_PER_RECOGNITION_ACCOUNT_SELECTION,
) -> list[dict[str, Any]]:
    """Export the exact top-N candidate union for every non-empty filter selection.

    Each summary row is encoded as recognition and inclusive account-membership
    bitsets. DuckDB ranks all nine selection masks in one proof-equivalent query.
    """

    recognition_case = "case " + " ".join(
        f"when recognition_status = '{value}' then {1 << index}"
        for index, value in enumerate(recognition_statuses)
    ) + " else 0 end"
    account_bits = " + ".join(
        f"case when account_type = '{value}' then {1 << index} else 0 end"
        for index, value in enumerate(account_filters)
    )
    candidates = query_rows(
        connection,
        f"""
          with classified as (
            select
              *,
              {recognition_case} as recognition_bit,
              {account_bits} as account_bits
            from counterparty_summary
          ),
          selections as (
            select recognition_mask, account_mask
            from range(1, {1 << len(recognition_statuses)}) as recognition(recognition_mask)
            cross join range(1, {1 << len(account_filters)}) as accounts(account_mask)
          ),
          ranked as (
            select
              selections.recognition_mask,
              selections.account_mask,
              classified.counterparty_address,
              sum(classified.transfer_count) as selected_transfer_count,
              max(classified.last_seen_at) as selected_last_seen_at
            from selections
            inner join classified
              on (classified.recognition_bit & selections.recognition_mask) != 0
              and (
                (classified.account_bits & selections.account_mask) != 0
                or selections.account_mask = {(1 << len(account_filters)) - 1}
              )
            group by
              selections.recognition_mask,
              selections.account_mask,
              classified.counterparty_address
            qualify row_number() over (
              partition by selections.recognition_mask, selections.account_mask
              order by
                selected_transfer_count desc,
                selected_last_seen_at desc,
                classified.counterparty_address
            ) <= {ranking_limit}
          )
          select distinct counterparty_address
          from ranked
        """,
    )
    candidate_addresses = {row["counterparty_address"] for row in candidates}

    if not candidate_addresses:
        return []

    ordered_addresses = sorted(candidate_addresses)
    placeholders = ", ".join("?" for _ in ordered_addresses)
    return query_rows(
        connection,
        f"""
          select
            chain_id,
            wallet_address,
            counterparty_address,
            account_type,
            code_state,
            observation_block_number,
            eip7702_delegation_target,
            recognition_status,
            transfer_count,
            inbound_transfer_count,
            outbound_transfer_count,
            token_count,
            first_seen_at,
            last_seen_at
          from counterparty_summary
          where counterparty_address in ({placeholders})
          order by transfer_count desc, last_seen_at desc, counterparty_address, recognition_status
        """,
        ordered_addresses,
    )


def values_for_mask(values: tuple[str, ...], mask: int) -> tuple[str, ...]:
    return tuple(value for index, value in enumerate(values) if mask & (1 << index))


def recognition_account_counts(connection: Any) -> dict[str, dict[str, int]]:
    """Return complete metrics for all nine non-empty composed filter selections."""

    rows_by_selection = query_rows(
        connection,
        f"""
          with classified as (
            select
              transaction_hash,
              token_address,
              counterparty_address,
              wallet_address,
              case
                when recognition_status = 'recognized' then 1
                when recognition_status = 'other' then 2
                else 0
              end as recognition_bit,
              case when counterparty_account_type = 'eoa_candidate' then 1 else 0 end
                + case when counterparty_account_type = 'contract' then 2 else 0 end
                as account_bits
            from wallet_events
          ),
          selections as (
            select recognition_mask, account_mask
            from range(1, {1 << len(RECOGNITION_STATUSES)}) as recognition(recognition_mask)
            cross join range(1, {1 << len(ACCOUNT_FILTERS)}) as accounts(account_mask)
          )
          select
            selections.recognition_mask,
            selections.account_mask,
            count(classified.transaction_hash) as transfer_count,
            count(distinct classified.token_address) as token_count,
            count(distinct classified.counterparty_address) filter (
              where classified.counterparty_address != classified.wallet_address
            ) as counterparty_count
          from selections
          left join classified
            on (classified.recognition_bit & selections.recognition_mask) != 0
            and (
              (classified.account_bits & selections.account_mask) != 0
              or selections.account_mask = {(1 << len(ACCOUNT_FILTERS)) - 1}
            )
          group by selections.recognition_mask, selections.account_mask
        """,
    )

    result: dict[str, dict[str, int]] = {}
    for row in rows_by_selection:
        recognition_key = "+".join(
            values_for_mask(RECOGNITION_STATUSES, row["recognition_mask"])
        )
        account_key = "+".join(values_for_mask(ACCOUNT_FILTERS, row["account_mask"]))
        result[f"{recognition_key}|{account_key}"] = {
            "transfer_count": row["transfer_count"],
            "token_count": row["token_count"],
            "counterparty_count": row["counterparty_count"],
        }
    return result


def main() -> None:
    if not DB_PATH.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "run_dbt.py"), "build"], check=True)

    duckdb = ensure_duckdb()
    connection = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        validate_export_schema(connection)
        events = query_rows(
            connection,
            f"""
              select
                cast(chain_id as varchar)
                  || '-' || transaction_hash
                  || '-' || cast(log_index as varchar) as transfer_id,
                chain_id,
                wallet_address,
                block_number,
                block_timestamp,
                transaction_hash,
                transaction_index,
                log_index,
                token_address,
                token_symbol,
                token_name,
                recognition_status,
                direction,
                is_indirect,
                counterparty_address,
                counterparty_account_type,
                counterparty_code_state,
                counterparty_observation_block_number,
                counterparty_eip7702_delegation_target
              from (
                select *, row_number() over (
                  partition by recognition_status, counterparty_account_type
                  order by block_number desc, transaction_index desc, log_index desc, transaction_hash desc
                ) as recognition_rank
                from wallet_events
              )
              where recognition_rank <= {EVENT_LIMIT_PER_RECOGNITION_ACCOUNT_EVIDENCE}
              order by block_number desc, transaction_index desc, log_index desc, transaction_hash desc
            """,
        )
        token_summaries = token_summary_rows(connection)
        counterparty_summaries = counterparty_rows(connection)
        timeline = query_rows(
            connection,
            f"""
              select
                chain_id,
                wallet_address,
                block_date,
                token_address,
                token_symbol,
                recognition_status,
                counterparty_account_type,
                direction,
                transfer_count
              from (
                select *, row_number() over (
                  partition by recognition_status, counterparty_account_type
                  order by block_date desc, token_symbol, direction, token_address
                ) as recognition_rank
                from timeline_daily
              )
              where recognition_rank <= {TIMELINE_ROW_LIMIT_PER_RECOGNITION_ACCOUNT_EVIDENCE}
              order by block_date, token_symbol, direction
            """,
        )
        metadata = query_rows(
            connection,
            """
              select
                configured_wallet_label,
                wallet_address,
                chain_id,
                data_source,
                generated_at,
                snapshot_run_id,
                snapshot_start_block,
                snapshot_end_block,
                snapshot_end_block_hash,
                snapshot_finality_policy,
                snapshot_scope_version,
                snapshot_source,
                snapshot_schema_version,
                wallet_attribution_source_url,
                transfer_count,
                event_block_number_min,
                event_block_number_max,
                first_event_at,
                last_event_at,
                account_evidence_population_scope,
                account_evidence_eligible_address_count,
                account_evidence_classified_address_count,
                account_evidence_failed_address_count,
                account_evidence_not_checked_address_count,
                account_evidence_eligible_event_count,
                account_evidence_classified_event_count,
                account_evidence_failed_event_count,
                account_evidence_not_checked_event_count,
                account_evidence_observation_block_number_min,
                account_evidence_observation_block_number_max,
                account_evidence_observation_block_timestamp_min,
                account_evidence_observation_block_timestamp_max,
                account_evidence_schema_version
              from pipeline_metadata
              order by chain_id, wallet_address
            """,
        )

        if len(metadata) != 1:
            raise RuntimeError(f"Expected one configured wallet, found {len(metadata)}")
        if metadata[0]["data_source"] != "fixture":
            raise RuntimeError("Static dashboard export requires fixture provenance")
        if metadata[0]["snapshot_schema_version"] != "mainnet-demo-snapshot-v1":
            raise RuntimeError("Static dashboard export requires the finalized mainnet demo snapshot")

        complete_export_counts = query_rows(
            connection,
            """
              select
                (select count(*) from wallet_events) as complete_event_count,
                (select count(*) from token_summary) as complete_token_summary_row_count,
                (select count(*) from counterparty_summary) as complete_counterparty_summary_row_count,
                (select count(*) from timeline_daily) as complete_timeline_row_count,
                (
                  select count(*) from (
                    select distinct recognition_status, counterparty_account_type
                    from wallet_events
                  )
                ) as recognition_account_evidence_cell_count
            """,
        )[0]
        if metadata[0]["transfer_count"] != complete_export_counts["complete_event_count"]:
            raise RuntimeError(
                "Pipeline metadata transfer count does not reconcile with wallet_events"
            )

        recognition_counts: dict[str, dict[str, int]] = {}
        for selected in non_empty_subsets(RECOGNITION_STATUSES):
            placeholders = ", ".join("?" for _ in selected)
            metrics = query_rows(
                connection,
                f"""
                  select
                    count(*) as transfer_count,
                    count(distinct token_address) as token_count,
                    count(distinct counterparty_address) filter (
                      where counterparty_address != wallet_address
                    ) as counterparty_count
                  from wallet_events
                  where recognition_status in ({placeholders})
                """,
                selected,
            )[0]
            recognition_counts["+".join(selected)] = metrics

        composed_filter_counts = recognition_account_counts(connection)

        meta = {
            **metadata[0],
            **complete_export_counts,
            "export_schema_version": EXPORT_SCHEMA_VERSION,
            "completeness_scope": "finalized_block_range",
            "indexer_checkpoint_recorded": True,
            "finality_status": "finalized",
            "recognition_counts": recognition_counts,
            "recognition_account_counts": composed_filter_counts,
            "exported_event_count": len(events),
            "exported_token_summary_count": len(token_summaries),
            "exported_counterparty_summary_count": len(counterparty_summaries),
            "exported_timeline_row_count": len(timeline),
            "event_export_limit_per_recognition_account_evidence": EVENT_LIMIT_PER_RECOGNITION_ACCOUNT_EVIDENCE,
            "token_summary_ranking_limit_per_recognition_account_selection": TOKEN_SUMMARY_RANKING_LIMIT_PER_RECOGNITION_ACCOUNT_SELECTION,
            "token_summary_ranking_selection_count": (
                len(non_empty_subsets(RECOGNITION_STATUSES))
                * len(non_empty_subsets(ACCOUNT_FILTERS))
            ),
            "token_summary_ranking_candidate_token_count": len({
                row["token_address"] for row in token_summaries
            }),
            "token_summary_rankings_exact_for_all_filter_selections": True,
            "counterparty_ranking_limit_per_recognition_account_selection": COUNTERPARTY_RANKING_LIMIT_PER_RECOGNITION_ACCOUNT_SELECTION,
            "counterparty_recognition_combination_count": len(non_empty_subsets(RECOGNITION_STATUSES)),
            "counterparty_account_filter_combination_count": len(non_empty_subsets(ACCOUNT_FILTERS)),
            "counterparty_ranking_selection_count": (
                len(non_empty_subsets(RECOGNITION_STATUSES))
                * len(non_empty_subsets(ACCOUNT_FILTERS))
            ),
            "counterparty_ranking_candidate_address_count": len({
                row["counterparty_address"] for row in counterparty_summaries
            }),
            "counterparty_rankings_exact_for_all_filter_selections": True,
            "timeline_row_export_limit_per_recognition_account_evidence": TIMELINE_ROW_LIMIT_PER_RECOGNITION_ACCOUNT_EVIDENCE,
        }
        meta["is_sampled"] = export_is_sampled(meta)

        write_json(
            "summaries.json",
            {
                "tokens": token_summaries,
                "counterparties": counterparty_summaries,
            },
        )
        write_json("timeline.json", timeline)
        write_json("events.json", events)
        write_json("meta.json", meta)
    finally:
        connection.close()

    print(f"Exported dashboard JSON to {PUBLIC_DATA}")


if __name__ == "__main__":
    main()
