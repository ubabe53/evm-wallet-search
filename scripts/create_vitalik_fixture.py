#!/usr/bin/env python3
"""Create the checked-in, sampled Vitalik ERC-20 snapshot from HyperIndex."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from project_config import resolved_runtime


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "analytics/fixtures/vitalik_erc20_transfers_90d.parquet"
VITALIK_ADDRESS = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
SNAPSHOT_DAYS = 90
ROWS_PER_DAY = 100
ADDRESS_RE = re.compile(r"^0x[0-9a-f]{40}$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    wallet_address = VITALIK_ADDRESS
    if not ADDRESS_RE.fullmatch(wallet_address):
        raise RuntimeError("Configured snapshot wallet must be a lowercase EVM address")

    dsn = resolved_runtime()["hyperindex_postgres_dsn"]
    if not dsn:
        raise SystemExit(
            "Set DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN or "
            "analytics.hyperindex_postgres_dsn in config.yaml."
        )

    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    manifest_path = output.with_suffix(".json")

    connection = duckdb.connect()
    connection.execute("INSTALL postgres")
    connection.execute("LOAD postgres")
    escaped_dsn = str(dsn).replace("'", "''")
    connection.execute(
        f"ATTACH '{escaped_dsn}' AS hyperindex (TYPE postgres, READ_ONLY)"
    )

    source_sql = f"""
      with windowed as (
        select
        id,
        chain_id,
        block_number,
        block_timestamp,
        transaction_hash,
        transaction_index,
        transaction_from_address,
        transaction_to_address,
        log_index,
        token_address,
        from_address,
        to_address,
          value_raw::text as value_raw
        from public."Erc20Transfer"
        where (
          lower(from_address) = '{wallet_address}'
          or lower(to_address) = '{wallet_address}'
        )
        and block_timestamp >= (
          select max(block_timestamp) - {SNAPSHOT_DAYS} * 86400
          from public."Erc20Transfer"
          where lower(from_address) = '{wallet_address}'
            or lower(to_address) = '{wallet_address}'
        )
      ),
      ranked as (
        select
          *,
          row_number() over (
            partition by (to_timestamp(block_timestamp) at time zone 'UTC')::date
            order by md5(id), id
          ) as sample_rank
        from windowed
      )
      select
        id,
        chain_id,
        block_number,
        block_timestamp,
        transaction_hash,
        transaction_index,
        transaction_from_address,
        transaction_to_address,
        log_index,
        token_address,
        from_address,
        to_address,
        value_raw
      from ranked
      where sample_rank <= {ROWS_PER_DAY}
      order by block_number, transaction_index, log_index, id
    """
    escaped_source_sql = source_sql.replace("'", "''")
    connection.execute(
        f"""
        copy (
          select * from postgres_query('hyperindex', '{escaped_source_sql}')
        ) to ? (
          format parquet,
          compression zstd,
          row_group_size 100000,
          overwrite_or_ignore true
        )
        """,
        [str(temporary)],
    )

    metrics = connection.execute(
        """
        select
          count(*) as row_count,
          count(distinct token_address) as token_contract_count,
          count(distinct case
            when lower(from_address) = ? then to_address else from_address
          end) as counterparty_count,
          min(block_number) as block_number_min,
          max(block_number) as block_number_max,
          epoch(min(to_timestamp(block_timestamp)))::bigint as timestamp_min,
          epoch(max(to_timestamp(block_timestamp)))::bigint as timestamp_max,
          count(*) filter (
            where transaction_from_address is not null
               or transaction_to_address is not null
          ) as transaction_envelope_populated_rows,
          count(*) filter (where regexp_matches(value_raw, '[eE]')) as exponent_value_count,
          count(*) filter (
            where lower(from_address) != ? and lower(to_address) != ?
          ) as unrelated_row_count
        from read_parquet(?)
        """,
        [wallet_address, wallet_address, wallet_address, str(temporary)],
    ).fetchone()
    if metrics[0] == 0 or metrics[8] != 0 or metrics[9] != 0:
        raise RuntimeError("Snapshot validation failed")

    temporary.replace(output)
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    manifest = {
        "fixture_kind": f"vitalik_{SNAPSHOT_DAYS}d",
        "chain_id": 1,
        "wallet_address": wallet_address,
        "source": "Envio HyperIndex public.Erc20Transfer",
        "window_policy": (
            f"latest indexed wallet timestamp minus {SNAPSHOT_DAYS} days, inclusive"
        ),
        "sampling_policy": (
            f"up to {ROWS_PER_DAY} rows per UTC day ordered by md5(id), then id"
        ),
        "source_is_sampled": True,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "row_count": metrics[0],
        "token_contract_count": metrics[1],
        "counterparty_count": metrics[2],
        "block_number_min": metrics[3],
        "block_number_max": metrics[4],
        "block_timestamp_min_utc": datetime.fromtimestamp(metrics[5], timezone.utc).isoformat(),
        "block_timestamp_max_utc": datetime.fromtimestamp(metrics[6], timezone.utc).isoformat(),
        "transaction_envelope_populated_rows": metrics[7],
        "transaction_envelope_note": (
            "Historical rows predate transaction envelope indexing; nullable sender "
            "and target evidence remains unknown."
        ),
        "parquet_sha256": checksum,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {metrics[0]:,} rows to {output}")


if __name__ == "__main__":
    main()
