#!/usr/bin/env python3
"""Rebuild live wallet projections after explicit shared account enrichment."""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

try:
    from .artifact_paths import LIVE_DB_PATH
    from .project_config import resolved_runtime
    from .run_dbt import EVM_WALLET_SCAN_ADDRESS_ENV, run_dbt
    from .snapshot_runs import SnapshotRun, dbt_snapshot_environment
except ImportError:
    from artifact_paths import LIVE_DB_PATH
    from project_config import resolved_runtime
    from run_dbt import EVM_WALLET_SCAN_ADDRESS_ENV, run_dbt
    from snapshot_runs import SnapshotRun, dbt_snapshot_environment


def cumulative_wallet_rebuild_scopes(
    database_path: Path = LIVE_DB_PATH,
) -> list[SnapshotRun]:
    """Use latest provenance but replace its interval with full completed coverage."""

    import duckdb

    if not database_path.is_file():
        raise RuntimeError("Live analytics database is missing; run app:up first")
    with duckdb.connect(str(database_path), read_only=True) as connection:
        rows = connection.execute(
            """
            with completed as (
              select *,
                min(from_block) over (partition by chain_id, wallet_address, scope_version) as coverage_start,
                row_number() over (
                  partition by chain_id, wallet_address, scope_version
                  order by to_block desc, completed_at desc
                ) as recency
              from ops.pipeline_runs
              where status = 'completed'
            )
            select run_id, chain_id, generation_id, wallet_address, wallet_label,
              coverage_start, to_block, to_block_hash, scope_version, original_input,
              normalized_name, resolver_source, observation_block_number,
              observation_block_hash, observation_timestamp
            from completed
            where recency = 1
            order by chain_id, wallet_address
            """
        ).fetchall()
    if not rows:
        raise RuntimeError("No completed live wallet snapshots are available to rebuild")
    return [
        SnapshotRun(
            run_id=str(row[0]),
            chain_id=int(row[1]),
            generation_id=str(row[2]),
            wallet_address=str(row[3]),
            wallet_label=str(row[4]),
            from_block=int(row[5]),
            to_block=int(row[6]),
            to_block_hash=str(row[7]),
            scope_version=str(row[8]),
            original_input=str(row[9] or row[4]),
            normalized_name=None if row[10] is None else str(row[10]),
            resolver_source=str(row[11]),
            observation_block_number=int(row[12]),
            observation_block_hash=str(row[13]),
            observation_timestamp=row[14],
        )
        for row in rows
    ]


def _relation_rows_equal(connection, previous: str, staged: str) -> bool:
    row = connection.execute(
        f"""
        select
          not exists (select * from {previous} except all select * from {staged})
          and not exists (select * from {staged} except all select * from {previous})
        """
    ).fetchone()
    return bool(row and row[0])


def validate_enrichment_rebuild(staged_path: Path, previous_path: Path) -> None:
    """Allow evidence projections to change while preserving durable product state."""

    import duckdb

    previous = str(previous_path).replace("'", "''")
    with duckdb.connect(str(staged_path), read_only=False) as connection:
        connection.execute(f"attach '{previous}' as previous_live (read_only)")
        try:
            for schema_name in ("ops", "app"):
                relations = connection.execute(
                    """
                    select table_name
                    from duckdb_tables()
                    where database_name = 'previous_live' and schema_name = ?
                    order by table_name
                    """,
                    [schema_name],
                ).fetchall()
                for (relation,) in relations:
                    staged_exists = connection.execute(
                        """
                        select count(*) from duckdb_tables()
                        where database_name = current_database() and schema_name = ? and table_name = ?
                        """,
                        [schema_name, relation],
                    ).fetchone()
                    if not staged_exists or staged_exists[0] != 1:
                        raise RuntimeError(
                            f"Enrichment rebuild dropped {schema_name}.{relation}"
                        )
                    if not _relation_rows_equal(
                        connection,
                        f'previous_live."{schema_name}"."{relation}"',
                        f'"{schema_name}"."{relation}"',
                    ):
                        raise RuntimeError(
                            f"Enrichment rebuild changed {schema_name}.{relation}"
                        )

            immutable_columns = """
              chain_id, wallet_address, block_number, block_hash, block_timestamp,
              transaction_hash, transaction_index, transaction_from_address,
              transaction_to_address, log_index, token_address, from_address,
              to_address, direction, counterparty_address, value_raw
            """
            if not _relation_rows_equal(
                connection,
                f"(select {immutable_columns} from previous_live.main.int_wallet_transfer_events)",
                f"(select {immutable_columns} from main.int_wallet_transfer_events)",
            ):
                raise RuntimeError("Enrichment rebuild changed immutable wallet event facts")

            metadata_columns = """
              chain_id, wallet_address, data_source, snapshot_run_id,
              snapshot_start_block, snapshot_end_block, snapshot_end_block_hash,
              snapshot_finality_policy, snapshot_scope_version, transfer_count
            """
            if not _relation_rows_equal(
                connection,
                f"(select {metadata_columns} from previous_live.main.pipeline_metadata)",
                f"(select {metadata_columns} from main.pipeline_metadata)",
            ):
                raise RuntimeError("Enrichment rebuild changed finalized wallet coverage")
        finally:
            connection.execute("detach previous_live")


WALLET_GRAINED_RELATIONS = (
    "int_wallet_transfer_events",
    "wallet_events",
    "token_summary",
    "counterparty_summary",
    "timeline_daily",
    "pipeline_metadata",
)


def restore_unselected_wallets(
    staged_path: Path, previous_iteration_path: Path, selected_wallet: str
) -> None:
    """Keep every other wallet byte-for-byte stable during one wallet rebuild."""

    import duckdb

    previous = str(previous_iteration_path).replace("'", "''")
    with duckdb.connect(str(staged_path), read_only=False) as connection:
        connection.execute(f"attach '{previous}' as previous_iteration (read_only)")
        try:
            connection.execute("begin transaction")
            for relation in WALLET_GRAINED_RELATIONS:
                connection.execute(
                    f"delete from main.{relation} where wallet_address != ?",
                    [selected_wallet],
                )
                connection.execute(
                    f"""
                    insert into main.{relation}
                    select * from previous_iteration.main.{relation}
                    where wallet_address != ?
                    """,
                    [selected_wallet],
                )
            connection.execute("commit")
        except BaseException:
            connection.execute("rollback")
            raise
        finally:
            connection.execute("detach previous_iteration")


def rebuild_live_enrichment(database_path: Path = LIVE_DB_PATH) -> None:
    runtime = resolved_runtime()
    dsn = str(runtime.get("wallet_scan_postgres_dsn") or "")
    if not dsn:
        raise RuntimeError("WALLET_SCAN_POSTGRES_DSN is required to rebuild live enrichment")
    cumulative_scopes = cumulative_wallet_rebuild_scopes(database_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="wallet-enrichment-", dir=str(database_path.parent)
    ) as directory:
        staged = Path(directory) / "live.duckdb"
        shutil.copy2(database_path, staged)
        for cumulative_scope in cumulative_scopes:
            # dbt_snapshot_environment reads from_block/to_block from this scope.
            # from_block is the wallet's earliest completed block, not the latest
            # run's start, so incremental delete+insert revisits every historical
            # event identity and reapplies the shared evidence join.
            previous_iteration = Path(
                directory
            ) / f"before-{cumulative_scope.wallet_address}.duckdb"
            shutil.copy2(staged, previous_iteration)
            run_dbt(
                "build",
                ["--vars", '{"use_fixture": false}'],
                use_hyperindex=True,
                hyperindex_dsn=dsn,
                extra_env=dbt_snapshot_environment(cumulative_scope)
                | {EVM_WALLET_SCAN_ADDRESS_ENV: cumulative_scope.wallet_address},
                database_path_override=staged,
            )
            restore_unselected_wallets(
                staged, previous_iteration, cumulative_scope.wallet_address
            )
            previous_iteration.unlink()
        validate_enrichment_rebuild(staged, database_path)
        os.replace(staged, database_path)


def main() -> None:
    rebuild_live_enrichment()
    print("Published refreshed account-evidence projections for every completed wallet")


if __name__ == "__main__":
    main()
