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
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "analytics" / "wallet_analytics.duckdb"
PUBLIC_DATA = ROOT / "public" / "data"

# Static JSON stays intentionally bounded; DuckDB remains the complete artifact.
EVENT_LIMIT_PER_STATUS = 1_000
GRAPH_INTERACTION_LIMIT_PER_STATUS = 250
TOKEN_SUMMARY_LIMIT_PER_STATUS = 500
COUNTERPARTY_SUMMARY_LIMIT = 500
TIMELINE_ROW_LIMIT = 5_000


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
        return float(value)
    return str(value)


def query_rows(connection: Any, query: str, parameters: list[Any] | None = None) -> list[dict[str, Any]]:
    result = connection.execute(query, parameters or [])
    columns = [column[0] for column in result.description]
    return [dict(zip(columns, row)) for row in result.fetchall()]


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
    if node["node_type"] in ("wallet", "counterparty") and node["address_type"]:
        return f"{label}\n{node['address_type']}"
    return label


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
                    "addressType": node["address_type"],
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
                    "metadataSource": edge["metadata_source"],
                    "metadataSourceUrl": edge["metadata_source_url"],
                    "tokenReputation": edge["token_reputation"],
                    "tokenReputationScore": edge["token_reputation_score"],
                    "tokenReputationReasons": edge["token_reputation_reasons"],
                    "interactionLegitimacy": edge["interaction_legitimacy"],
                    "interactionLegitimacyScore": edge["interaction_legitimacy_score"],
                    "interactionLegitimacyReasons": edge["interaction_legitimacy_reasons"],
                    "transferCount": edge["transfer_count"],
                    "counterpartyTransferCount": edge["counterparty_transfer_count"],
                    "amountDecimalSum": edge["amount_decimal_sum"],
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
            partition by max(token_status)
            order by max(transfer_count) desc, max(last_seen_at) desc, interaction_id
          ) as status_rank
        from graph_edges
        group by interaction_id
      )
      where status_rank <= {GRAPH_INTERACTION_LIMIT_PER_STATUS}
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


def main() -> None:
    if not DB_PATH.exists():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "run_dbt.py"), "build"], check=True)

    duckdb = ensure_duckdb()
    connection = duckdb.connect(str(DB_PATH), read_only=True)

    try:
        nodes, edges = graph_rows(connection)
        events = query_rows(
            connection,
            f"""
              select * exclude (status_rank)
              from (
                select *, row_number() over (
                  partition by token_status
                  order by block_timestamp desc, transaction_hash, log_index
                ) as status_rank
                from wallet_events
              )
              where status_rank <= {EVENT_LIMIT_PER_STATUS}
              order by block_timestamp desc, transaction_hash, log_index
            """,
        )
        token_summaries = query_rows(
            connection,
            f"""
              select * exclude (status_rank)
              from (
                select *, row_number() over (
                  partition by token_status
                  order by transfer_count desc, token_symbol, direction
                ) as status_rank
                from token_summary
              )
              where status_rank <= {TOKEN_SUMMARY_LIMIT_PER_STATUS}
              order by transfer_count desc, token_symbol, direction
            """,
        )
        counterparty_summaries = rows(
            connection,
            "counterparty_summary",
            "transfer_count desc, last_seen_at desc, counterparty_address",
            COUNTERPARTY_SUMMARY_LIMIT,
        )
        timeline = query_rows(
            connection,
            f"""
              select *
              from (
                select * from timeline_daily
                order by block_date desc, token_symbol, direction
                limit {TIMELINE_ROW_LIMIT}
              )
              order by block_date, token_symbol, direction
            """,
        )
        metadata = rows(connection, "pipeline_metadata", "wallet_id")

        if len(metadata) != 1:
            raise RuntimeError(f"Expected one configured wallet, found {len(metadata)}")

        complete_export_counts = query_rows(
            connection,
            """
              select
                (select count(*) from token_summary) as token_summary_row_count,
                (select count(*) from counterparty_summary) as counterparty_summary_row_count
            """,
        )[0]

        statuses = ("trusted", "unverified", "suspected_spam", "spam")
        status_counts: dict[str, dict[str, int]] = {}
        for mask in range(1, 1 << len(statuses)):
            selected = [status for index, status in enumerate(statuses) if mask & (1 << index)]
            placeholders = ", ".join("?" for _ in selected)
            metrics = query_rows(
                connection,
                f"""
                  select
                    count(*) as transfer_count,
                    count(distinct token_address) as token_count,
                    count(distinct counterparty_address) as counterparty_count
                  from wallet_events
                  where token_status in ({placeholders})
                """,
                selected,
            )[0]
            status_counts["+".join(selected)] = metrics

        meta = {
            **metadata[0],
            **complete_export_counts,
            "status_counts": status_counts,
            "exported_event_count": len(events),
            "exported_interaction_count": len({edge["interaction_id"] for edge in edges}),
            "exported_token_summary_count": len(token_summaries),
            "exported_counterparty_summary_count": len(counterparty_summaries),
            "exported_timeline_row_count": len(timeline),
            "event_export_limit_per_status": EVENT_LIMIT_PER_STATUS,
            "graph_interaction_export_limit_per_status": GRAPH_INTERACTION_LIMIT_PER_STATUS,
            "token_summary_export_limit_per_status": TOKEN_SUMMARY_LIMIT_PER_STATUS,
            "counterparty_summary_export_limit": COUNTERPARTY_SUMMARY_LIMIT,
            "timeline_row_export_limit": TIMELINE_ROW_LIMIT,
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
