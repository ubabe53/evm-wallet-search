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
EVENT_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE = 1_000
GRAPH_INTERACTION_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE = 250
TOKEN_SUMMARY_RANKING_LIMIT_PER_STATUS_QUALITY_ACCOUNT_SELECTION = 500
COUNTERPARTY_RANKING_LIMIT_PER_STATUS_QUALITY_ACCOUNT_SELECTION = 50
TIMELINE_ROW_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE = 5_000
TOKEN_STATUSES = ("trusted", "unverified", "suspected_spam", "spam")
TOKEN_QUALITIES = ("high_confidence", "listed", "unknown")
ACCOUNT_FILTERS = ("eoa_candidate", "contract")
REQUIRED_EXPORT_COLUMNS = {
    "wallet_events": {
        "from_address",
        "to_address",
        "value_raw",
        "transaction_from_address",
        "transaction_to_address",
        "transaction_sender_relation",
        "transaction_target_relation",
        "is_indirect",
        "token_quality",
        "counterparty_account_type",
    },
    "token_summary": {
        "indirect_inbound_transfer_count",
        "indirect_outbound_transfer_count",
        "self_transfer_count",
        "value_raw_sum",
        "token_quality",
        "counterparty_account_type",
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


def rows(
    connection: Any,
    table: str,
    order_by: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    query = f"select * from {table}"
    if order_by:
        query += f" order by {order_by}"
    if limit is not None:
        query += f" limit {limit}"
    return query_rows(connection, query)


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
        ("exported_event_count", "transfer_count"),
        ("exported_interaction_count", "interaction_count"),
        ("exported_token_summary_count", "token_summary_row_count"),
        ("exported_counterparty_summary_count", "counterparty_summary_row_count"),
        ("exported_timeline_row_count", "timeline_row_count"),
    )
    return any(metadata[exported] < metadata[complete] for exported, complete in count_pairs)


def display_label(node: dict[str, Any]) -> str:
    """Keep graph labels readable while preserving full addresses in node data."""

    label = node["label"]
    if node["node_type"] == "counterparty" and isinstance(label, str) and len(label) == 42:
        label = f"{label[:6]}...{label[-4:]}"
    if node["node_type"] == "counterparty" and node["account_type"]:
        type_label = {"eoa_candidate": "EOA", "contract": "Contract"}.get(node["account_type"])
        return f"{label}\n{type_label}" if type_label else label
    return label


def non_empty_subsets(values: tuple[str, ...]) -> list[tuple[str, ...]]:
    return [
        tuple(value for index, value in enumerate(values) if mask & (1 << index))
        for mask in range(1, 1 << len(values))
    ]


def build_graph(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "nodes": [
            {
                "data": {
                    "id": node["node_id"],
                    "label": display_label(node),
                    "type": node["node_type"],
                    "address": node["address"],
                    "tokenAddress": node["token_address"],
                    "symbol": node["symbol"],
                    "accountType": node["account_type"],
                    "codeState": node["code_state"],
                    "observationBlockNumber": node["observation_block_number"],
                    "observationBlockTimestamp": node["observation_block_timestamp"],
                    "eip7702DelegationTarget": node["eip7702_delegation_target"],
                    "evidenceFetchStatus": node["evidence_fetch_status"],
                    "evidenceReasonCodes": node["evidence_reason_codes"],
                }
            }
            for node in nodes
        ],
        "edges": [
            {
                "data": {
                    "id": edge["edge_id"],
                    "interactionId": edge["interaction_id"],
                    "edgeRole": edge["edge_role"],
                    "source": edge["source_node_id"],
                    "target": edge["target_node_id"],
                    "walletAddress": edge["wallet_address"],
                    "counterpartyAddress": edge["counterparty_address"],
                    "direction": edge["direction"],
                    "tokenAddress": edge["token_address"],
                    "tokenSymbol": edge["token_symbol"],
                    "tokenStatus": edge["token_status"],
                    "recognitionStatus": edge["recognition_status"],
                    "recognitionSource": edge["recognition_source"],
                    "recognitionOverrideStatus": None,
                    "metadataAvailability": edge["metadata_availability"],
                    "tokenQuality": edge["token_quality"],
                    "tokenQualitySources": edge["token_quality_sources"],
                    "tokenQualitySourceCount": edge["token_quality_source_count"],
                    "tokenQualityReason": edge["token_quality_reason"],
                    "tokenQualityProvenance": edge["token_quality_provenance"],
                    "tokenQualityVersion": edge["token_quality_version"],
                    "metadataSource": edge["metadata_source"],
                    "metadataSourceUrl": edge["metadata_source_url"],
                    "counterpartyAccountType": edge["counterparty_account_type"],
                    "transferCount": edge["transfer_count"],
                    "counterpartyTransferCount": edge["counterparty_transfer_count"],
                }
            }
            for edge in edges
        ],
    }


def graph_rows(connection: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Select both legs and endpoint nodes for the highest-activity interactions."""

    ranked_interactions = f"""
      select interaction_id
      from (
        select
          interaction_id,
          row_number() over (
            partition by
              max(token_status),
              max(token_quality),
              max(counterparty_account_type)
            order by max(transfer_count) desc, max(last_seen_at) desc, interaction_id
          ) as status_rank
        from graph_edges
        group by interaction_id
      )
      where status_rank <= {GRAPH_INTERACTION_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE}
    """
    edges = query_rows(
        connection,
        f"""
          select edges.*
          from graph_edges as edges
          inner join ({ranked_interactions}) as selected using (interaction_id)
          order by edges.transfer_count desc, edges.edge_id
        """,
    )
    nodes = query_rows(
        connection,
        f"""
          with selected_edges as (
            select edges.*
            from graph_edges as edges
            inner join ({ranked_interactions}) as selected using (interaction_id)
          ),
          endpoint_ids as (
            select source_node_id as node_id from selected_edges
            union
            select target_node_id as node_id from selected_edges
          )
          select nodes.*
          from graph_nodes as nodes
          inner join endpoint_ids using (node_id)
          order by nodes.node_type, nodes.label
        """,
    )
    return nodes, edges


def token_summary_rows(
    connection: Any,
    statuses: tuple[str, ...] = TOKEN_STATUSES,
    qualities: tuple[str, ...] = TOKEN_QUALITIES,
    account_filters: tuple[str, ...] = ACCOUNT_FILTERS,
    ranking_limit: int = TOKEN_SUMMARY_RANKING_LIMIT_PER_STATUS_QUALITY_ACCOUNT_SELECTION,
) -> list[dict[str, Any]]:
    """Export per-cell rows for the exact token top-N union of every filter selection."""

    status_case = "case " + " ".join(
        f"when token_status = '{value}' then {1 << index}"
        for index, value in enumerate(statuses)
    ) + " else 0 end"
    quality_case = "case " + " ".join(
        f"when token_quality = '{value}' then {1 << index}"
        for index, value in enumerate(qualities)
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
              {status_case} as status_bit,
              {quality_case} as quality_bit,
              {account_bits} as account_bits
            from token_summary
          ),
          selections as (
            select status_mask, quality_mask, account_mask
            from range(1, {1 << len(statuses)}) as statuses(status_mask)
            cross join range(1, {1 << len(qualities)}) as qualities(quality_mask)
            cross join range(1, {1 << len(account_filters)}) as accounts(account_mask)
          ),
          ranked as (
            select
              selections.status_mask,
              selections.quality_mask,
              selections.account_mask,
              classified.token_address,
              sum(classified.transfer_count) as selected_transfer_count
            from selections
            inner join classified
              on (classified.status_bit & selections.status_mask) != 0
              and (classified.quality_bit & selections.quality_mask) != 0
              and (
                (classified.account_bits & selections.account_mask) != 0
                or selections.account_mask = {(1 << len(account_filters)) - 1}
              )
            group by
              selections.status_mask,
              selections.quality_mask,
              selections.account_mask,
              classified.token_address
            qualify row_number() over (
              partition by selections.status_mask, selections.quality_mask, selections.account_mask
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
          select *
          from token_summary
          where token_address in ({placeholders})
          order by transfer_count desc, token_symbol, token_address, counterparty_account_type
        """,
        ordered_addresses,
    )


def counterparty_rows(
    connection: Any,
    statuses: tuple[str, ...] = TOKEN_STATUSES,
    qualities: tuple[str, ...] = TOKEN_QUALITIES,
    account_filters: tuple[str, ...] = ACCOUNT_FILTERS,
    ranking_limit: int = COUNTERPARTY_RANKING_LIMIT_PER_STATUS_QUALITY_ACCOUNT_SELECTION,
) -> list[dict[str, Any]]:
    """Export the exact top-N candidate union for every non-empty filter selection.

    Each summary row is encoded as status, quality, and inclusive account-membership
    bitsets. DuckDB ranks all selection masks in one proof-equivalent query, avoiding
    315 Python/SQL round trips without weakening the top-N guarantee.
    """

    status_case = "case " + " ".join(
        f"when token_status = '{value}' then {1 << index}"
        for index, value in enumerate(statuses)
    ) + " else 0 end"
    quality_case = "case " + " ".join(
        f"when token_quality = '{value}' then {1 << index}"
        for index, value in enumerate(qualities)
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
              {status_case} as status_bit,
              {quality_case} as quality_bit,
              {account_bits} as account_bits
            from counterparty_summary
          ),
          selections as (
            select status_mask, quality_mask, account_mask
            from range(1, {1 << len(statuses)}) as statuses(status_mask)
            cross join range(1, {1 << len(qualities)}) as qualities(quality_mask)
            cross join range(1, {1 << len(account_filters)}) as accounts(account_mask)
          ),
          ranked as (
            select
              selections.status_mask,
              selections.quality_mask,
              selections.account_mask,
              classified.counterparty_address,
              sum(classified.transfer_count) as selected_transfer_count,
              max(classified.last_seen_at) as selected_last_seen_at
            from selections
            inner join classified
              on (classified.status_bit & selections.status_mask) != 0
              and (classified.quality_bit & selections.quality_mask) != 0
              and (
                (classified.account_bits & selections.account_mask) != 0
                or selections.account_mask = {(1 << len(account_filters)) - 1}
              )
            group by
              selections.status_mask,
              selections.quality_mask,
              selections.account_mask,
              classified.counterparty_address
            qualify row_number() over (
              partition by selections.status_mask, selections.quality_mask, selections.account_mask
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
          select *
          from counterparty_summary
          where counterparty_address in ({placeholders})
          order by transfer_count desc, last_seen_at desc, counterparty_address, token_status, token_quality
        """,
        ordered_addresses,
    )


def values_for_mask(values: tuple[str, ...], mask: int) -> tuple[str, ...]:
    return tuple(value for index, value in enumerate(values) if mask & (1 << index))


def status_quality_account_counts(connection: Any) -> dict[str, dict[str, int]]:
    """Return complete metrics for all 315 non-empty composed filter selections."""

    rows_by_selection = query_rows(
        connection,
        f"""
          with classified as (
            select
              transfer_id,
              token_address,
              counterparty_address,
              wallet_address,
              case
                when token_status = 'trusted' then 1
                when token_status = 'unverified' then 2
                when token_status = 'suspected_spam' then 4
                when token_status = 'spam' then 8
                else 0
              end as status_bit,
              case
                when token_quality = 'high_confidence' then 1
                when token_quality = 'listed' then 2
                when token_quality = 'unknown' then 4
                else 0
              end as quality_bit,
              case when counterparty_account_type = 'eoa_candidate' then 1 else 0 end
                + case when counterparty_account_type = 'contract' then 2 else 0 end
                as account_bits
            from wallet_events
          ),
          selections as (
            select status_mask, quality_mask, account_mask
            from range(1, {1 << len(TOKEN_STATUSES)}) as statuses(status_mask)
            cross join range(1, {1 << len(TOKEN_QUALITIES)}) as qualities(quality_mask)
            cross join range(1, {1 << len(ACCOUNT_FILTERS)}) as accounts(account_mask)
          )
          select
            selections.status_mask,
            selections.quality_mask,
            selections.account_mask,
            count(classified.transfer_id) as transfer_count,
            count(distinct classified.token_address) as token_count,
            count(distinct classified.counterparty_address) filter (
              where classified.counterparty_address != classified.wallet_address
            ) as counterparty_count
          from selections
          left join classified
            on (classified.status_bit & selections.status_mask) != 0
            and (classified.quality_bit & selections.quality_mask) != 0
            and (
              (classified.account_bits & selections.account_mask) != 0
              or selections.account_mask = {(1 << len(ACCOUNT_FILTERS)) - 1}
            )
          group by selections.status_mask, selections.quality_mask, selections.account_mask
        """,
    )

    result: dict[str, dict[str, int]] = {}
    for row in rows_by_selection:
        status_key = "+".join(values_for_mask(TOKEN_STATUSES, row["status_mask"]))
        quality_key = "+".join(values_for_mask(TOKEN_QUALITIES, row["quality_mask"]))
        account_key = "+".join(values_for_mask(ACCOUNT_FILTERS, row["account_mask"]))
        result[f"{status_key}|{quality_key}|{account_key}"] = {
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
        nodes, edges = graph_rows(connection)
        events = query_rows(
            connection,
            f"""
              select * exclude (status_rank)
              from (
                select *, row_number() over (
                  partition by token_status, token_quality, counterparty_account_type
                  order by block_timestamp desc, transaction_hash, log_index
                ) as status_rank
                from wallet_events
              )
              where status_rank <= {EVENT_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE}
              order by block_timestamp desc, transaction_hash, log_index
            """,
        )
        token_summaries = token_summary_rows(connection)
        counterparty_summaries = counterparty_rows(connection)
        timeline = query_rows(
            connection,
            f"""
              select * exclude (status_quality_rank)
              from (
                select *, row_number() over (
                  partition by token_status, token_quality, counterparty_account_type
                  order by block_date desc, token_symbol, direction, token_address
                ) as status_quality_rank
                from timeline_daily
              )
              where status_quality_rank <= {TIMELINE_ROW_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE}
              order by block_date, token_symbol, direction
            """,
        )
        metadata = rows(connection, "pipeline_metadata", "chain_id, wallet_address")

        if len(metadata) != 1:
            raise RuntimeError(f"Expected one configured wallet, found {len(metadata)}")

        complete_export_counts = query_rows(
            connection,
            """
              select
                (select count(*) from token_summary) as token_summary_row_count,
                (select count(*) from counterparty_summary) as counterparty_summary_row_count,
                (
                  select count(*) from (
                    select distinct token_status, token_quality, counterparty_account_type
                    from wallet_events
                  )
                ) as status_quality_account_evidence_cell_count
            """,
        )[0]

        status_counts: dict[str, dict[str, int]] = {}
        for selected in non_empty_subsets(TOKEN_STATUSES):
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
                  where token_status in ({placeholders})
                """,
                selected,
            )[0]
            status_counts["+".join(selected)] = metrics

        quality_counts: dict[str, dict[str, int]] = {}
        for selected in non_empty_subsets(TOKEN_QUALITIES):
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
                  where token_quality in ({placeholders})
                """,
                selected,
            )[0]
            quality_counts["+".join(selected)] = metrics

        status_quality_counts: dict[str, dict[str, int]] = {}
        for selected_statuses in non_empty_subsets(TOKEN_STATUSES):
            status_placeholders = ", ".join("?" for _ in selected_statuses)
            for selected_qualities in non_empty_subsets(TOKEN_QUALITIES):
                quality_placeholders = ", ".join("?" for _ in selected_qualities)
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
                      where token_status in ({status_placeholders})
                        and token_quality in ({quality_placeholders})
                    """,
                    [*selected_statuses, *selected_qualities],
                )[0]
                key = f"{'+'.join(selected_statuses)}|{'+'.join(selected_qualities)}"
                status_quality_counts[key] = metrics

        composed_filter_counts = status_quality_account_counts(connection)

        meta = {
            **metadata[0],
            **complete_export_counts,
            "status_counts": status_counts,
            "quality_counts": quality_counts,
            "status_quality_counts": status_quality_counts,
            "status_quality_account_counts": composed_filter_counts,
            "exported_event_count": len(events),
            "exported_interaction_count": len({edge["interaction_id"] for edge in edges}),
            "exported_token_summary_count": len(token_summaries),
            "exported_counterparty_summary_count": len(counterparty_summaries),
            "exported_timeline_row_count": len(timeline),
            "event_export_limit_per_status_quality_account_evidence": EVENT_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE,
            "graph_interaction_export_limit_per_status_quality_account_evidence": GRAPH_INTERACTION_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE,
            "token_summary_ranking_limit_per_status_quality_account_selection": TOKEN_SUMMARY_RANKING_LIMIT_PER_STATUS_QUALITY_ACCOUNT_SELECTION,
            "token_summary_ranking_selection_count": (
                len(non_empty_subsets(TOKEN_STATUSES))
                * len(non_empty_subsets(TOKEN_QUALITIES))
                * len(non_empty_subsets(ACCOUNT_FILTERS))
            ),
            "token_summary_ranking_candidate_token_count": len({
                row["token_address"] for row in token_summaries
            }),
            "token_summary_rankings_exact_for_all_filter_selections": True,
            "counterparty_ranking_limit_per_status_quality_account_selection": COUNTERPARTY_RANKING_LIMIT_PER_STATUS_QUALITY_ACCOUNT_SELECTION,
            "counterparty_token_status_combination_count": len(non_empty_subsets(TOKEN_STATUSES)),
            "counterparty_token_quality_combination_count": len(non_empty_subsets(TOKEN_QUALITIES)),
            "counterparty_account_filter_combination_count": len(non_empty_subsets(ACCOUNT_FILTERS)),
            "counterparty_ranking_selection_count": (
                len(non_empty_subsets(TOKEN_STATUSES))
                * len(non_empty_subsets(TOKEN_QUALITIES))
                * len(non_empty_subsets(ACCOUNT_FILTERS))
            ),
            "counterparty_ranking_candidate_address_count": len({
                row["counterparty_address"] for row in counterparty_summaries
            }),
            "counterparty_rankings_exact_for_all_filter_selections": True,
            "timeline_row_export_limit_per_status_quality_account_evidence": TIMELINE_ROW_LIMIT_PER_STATUS_QUALITY_ACCOUNT_EVIDENCE,
        }
        meta["is_sampled"] = export_is_sampled(meta)

        write_json("graph.json", build_graph(nodes, edges))
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
