"""Merge isolated finalized Envio rows into shared Postgres raw persistence."""

from __future__ import annotations

import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator

CHAIN_ID = 1
SCOPE_VERSION = "wallet-transfer-signature-v1"
ADDRESS_PATTERN = re.compile(r"^0x[0-9a-f]{40}$")
HASH_PATTERN = re.compile(r"^0x[0-9a-f]{64}$")
TEMP_SCHEMA_PATTERN = re.compile(r"^wallet_scan_[a-z0-9_]+$")
SHARED_SCHEMA = "wallet_scan"


@dataclass(frozen=True)
class RawIngestionInterval:
    wallet_address: str
    from_block: int
    to_block: int
    to_block_hash: str
    scope_version: str = SCOPE_VERSION

    def validate(self) -> None:
        if not ADDRESS_PATTERN.fullmatch(self.wallet_address):
            raise ValueError("Raw ingestion wallet must be a canonical Ethereum address")
        if self.from_block < 0 or self.to_block < self.from_block:
            raise ValueError("Raw ingestion blocks must satisfy 0 <= from_block <= to_block")
        if not HASH_PATTERN.fullmatch(self.to_block_hash):
            raise ValueError("Raw ingestion end block hash must be canonical")
        if self.scope_version != SCOPE_VERSION:
            raise ValueError("Raw ingestion scope version is unsupported")


def validate_temporary_schema(schema_name: str) -> str:
    if not TEMP_SCHEMA_PATTERN.fullmatch(schema_name):
        raise ValueError("Temporary schema must use the wallet_scan_<job> namespace")
    return schema_name


def verify_finalized_hash(
    interval: RawIngestionInterval,
    finalized_hash_resolver: Callable[[int], str],
) -> None:
    """Require authoritative finalized evidence for the checkpoint endpoint."""

    interval.validate()
    observed_hash = finalized_hash_resolver(interval.to_block).strip().lower()
    if not HASH_PATTERN.fullmatch(observed_hash):
        raise RuntimeError("Finalized block hash resolver returned an invalid hash")
    if observed_hash != interval.to_block_hash:
        raise RuntimeError("Bounded scan end block no longer matches finalized chain evidence")


def validate_indexer_checkpoint(
    row: tuple[Any, ...] | None,
    interval: RawIngestionInterval,
) -> None:
    """Reject missing, partial, or differently configured Envio progress."""

    interval.validate()
    if row is None or len(row) != 5:
        raise RuntimeError("Bounded indexer did not persist one Ethereum progress checkpoint")
    chain_id, start_block, end_block, progress_block, ready_at = row
    if (
        int(chain_id) != CHAIN_ID
        or int(start_block) != interval.from_block
        or end_block is None
        or int(end_block) != interval.to_block
        or int(progress_block) < interval.to_block
        or ready_at is None
    ):
        raise RuntimeError("Bounded indexer did not complete the requested block interval")


def verify_bounded_indexer_completion(
    dsn: str,
    *,
    schema_name: str,
    interval: RawIngestionInterval,
) -> None:
    """Read Envio-owned progress before accepting an isolated bounded schema."""

    schema = validate_temporary_schema(schema_name)
    with postgres_connection(dsn, read_only=True) as connection:
        rows = connection.execute(
            f"""
            select id, start_block, end_block, progress_block, ready_at
            from shared.{schema}.envio_chains
            order by id
            """
        ).fetchall()
    row = rows[0] if len(rows) == 1 else None
    validate_indexer_checkpoint(row, interval)


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


@contextmanager
def postgres_connection(dsn: str, *, read_only: bool) -> Iterator[Any]:
    import duckdb

    escaped_dsn = dsn.replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute("install postgres; load postgres")
        mode = ", read_only" if read_only else ""
        connection.execute(
            f"attach '{escaped_dsn}' as shared (type postgres{mode})"
        )
        yield connection


def shared_raw_store_exists(dsn: str) -> bool:
    """Return whether the optional bounded-scan raw relation exists."""

    with postgres_connection(dsn, read_only=True) as connection:
        row = connection.execute(
            """
            select count(*)
            from shared.information_schema.tables
            where table_schema = ? and table_name = 'transfer_events'
            """,
            [SHARED_SCHEMA],
        ).fetchone()
    return bool(row is not None and row[0])


def completed_ingestion(dsn: str, interval: RawIngestionInterval) -> int | None:
    """Return the durable raw count for an exactly completed interval."""

    interval.validate()
    if not shared_raw_store_exists(dsn):
        return None
    with postgres_connection(dsn, read_only=True) as connection:
        row = connection.execute(
            """
            select raw_events_found
            from shared.wallet_scan.ingestion_runs
            where chain_id = 1 and wallet_address = ? and from_block = ? and to_block = ?
              and to_block_hash = ? and scope_version = ? and status = 'completed'
            """,
            [
                interval.wallet_address,
                interval.from_block,
                interval.to_block,
                interval.to_block_hash,
                interval.scope_version,
            ],
        ).fetchone()
    return None if row is None else int(row[0])


def merge_sql(schema_name: str, interval: RawIngestionInterval) -> str:
    """Build one transactional server-side merge for a validated temporary schema."""

    schema = validate_temporary_schema(schema_name)
    interval.validate()
    wallet = _sql_literal(interval.wallet_address)
    end_hash = _sql_literal(interval.to_block_hash)
    scope = _sql_literal(interval.scope_version)
    return f"""
create schema if not exists {SHARED_SCHEMA};
create table if not exists {SHARED_SCHEMA}.transfer_events (
  chain_id integer not null check (chain_id = 1),
  block_number bigint not null,
  block_hash text not null,
  block_timestamp bigint not null,
  transaction_hash text not null,
  transaction_index integer not null,
  transaction_from_address text,
  transaction_to_address text,
  log_index integer not null,
  token_address text not null,
  from_address text not null,
  to_address text not null,
  value_raw numeric not null,
  primary key (chain_id, transaction_hash, log_index)
);
create table if not exists {SHARED_SCHEMA}.ingestion_runs (
  chain_id integer not null check (chain_id = 1),
  wallet_address text not null,
  from_block bigint not null,
  to_block bigint not null,
  to_block_hash text not null,
  scope_version text not null,
  raw_events_found bigint not null check (raw_events_found >= 0),
  status text not null check (status = 'completed'),
  completed_at timestamptz not null default current_timestamp,
  primary key (chain_id, wallet_address, from_block, to_block, scope_version)
);
do $wallet_scan_validation$
begin
  if (select count(*) from {schema}.envio_chains) <> 1
     or not exists (
       select 1 from {schema}.envio_chains
       where id = 1 and start_block = {interval.from_block}
         and end_block = {interval.to_block}
         and progress_block >= {interval.to_block} and ready_at is not null
     ) then
    raise exception 'bounded indexer did not complete the requested block interval';
  end if;
  if exists (
    select 1 from {schema}."Erc20Transfer"
    where chain_id <> 1
       or block_number < {interval.from_block}
       or block_number > {interval.to_block}
       or (lower(from_address) <> {wallet} and lower(to_address) <> {wallet})
  ) then
    raise exception 'bounded scan rows violate the requested wallet/range';
  end if;
  if exists (
    select 1
    from {schema}."Erc20Transfer" incoming
    join {SHARED_SCHEMA}.transfer_events existing
      on existing.chain_id = incoming.chain_id
     and existing.transaction_hash = lower(incoming.transaction_hash)
     and existing.log_index = incoming.log_index
    where existing.block_number is distinct from incoming.block_number
       or existing.block_hash is distinct from lower(incoming.block_hash)
       or existing.block_timestamp is distinct from incoming.block_timestamp
       or existing.transaction_index is distinct from incoming.transaction_index
       or existing.transaction_from_address is distinct from lower(incoming.transaction_from_address)
       or existing.transaction_to_address is distinct from lower(incoming.transaction_to_address)
       or existing.token_address is distinct from lower(incoming.token_address)
       or existing.from_address is distinct from lower(incoming.from_address)
       or existing.to_address is distinct from lower(incoming.to_address)
       or existing.value_raw is distinct from incoming.value_raw
  ) then
    raise exception 'bounded scan conflicts with shared raw event identity';
  end if;
  if exists (
    select 1 from {SHARED_SCHEMA}.ingestion_runs
    where chain_id = 1 and wallet_address = {wallet}
      and from_block = {interval.from_block} and to_block = {interval.to_block}
      and scope_version = {scope} and to_block_hash <> {end_hash}
  ) then
    raise exception 'bounded scan interval already has a different finalized hash';
  end if;
end
$wallet_scan_validation$;
insert into {SHARED_SCHEMA}.transfer_events (
  chain_id, block_number, block_hash, block_timestamp, transaction_hash,
  transaction_index, transaction_from_address, transaction_to_address, log_index,
  token_address, from_address, to_address, value_raw
)
select
  chain_id, block_number, lower(block_hash), block_timestamp, lower(transaction_hash),
  transaction_index, lower(transaction_from_address), lower(transaction_to_address), log_index,
  lower(token_address), lower(from_address), lower(to_address), value_raw
from {schema}."Erc20Transfer"
on conflict (chain_id, transaction_hash, log_index) do nothing;
insert into {SHARED_SCHEMA}.ingestion_runs (
  chain_id, wallet_address, from_block, to_block, to_block_hash,
  scope_version, raw_events_found, status
)
select 1, {wallet}, {interval.from_block}, {interval.to_block}, {end_hash}, {scope}, count(*), 'completed'
from {schema}."Erc20Transfer"
on conflict (chain_id, wallet_address, from_block, to_block, scope_version)
do update set raw_events_found = excluded.raw_events_found,
              to_block_hash = excluded.to_block_hash,
              status = 'completed', completed_at = current_timestamp;
""".strip()


def merge_bounded_ingestion(
    dsn: str,
    *,
    schema_name: str,
    interval: RawIngestionInterval,
    finalized_hash_resolver: Callable[[int], str],
) -> int:
    """Validate, deduplicate, merge, and checkpoint one bounded Envio schema."""

    verify_bounded_indexer_completion(
        dsn,
        schema_name=schema_name,
        interval=interval,
    )
    verify_finalized_hash(interval, finalized_hash_resolver)
    sql = merge_sql(schema_name, interval)
    with postgres_connection(dsn, read_only=False) as connection:
        connection.execute(
            "call postgres_execute('shared', ?, true)",
            [sql],
        )
    completed = completed_ingestion(dsn, interval)
    if completed is None:
        raise RuntimeError("Bounded raw ingestion did not persist its completion checkpoint")
    return completed


def drop_temporary_schema(dsn: str, schema_name: str) -> None:
    """Drop only one validated bounded-job schema after its rows are merged or rejected."""

    schema = validate_temporary_schema(schema_name)
    with postgres_connection(dsn, read_only=False) as connection:
        connection.execute(
            "call postgres_execute('shared', ?, true)",
            [f'drop schema if exists {schema} cascade'],
        )
