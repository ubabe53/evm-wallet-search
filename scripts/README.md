# Scripts

This component owns explicit command-line orchestration around indexing, dbt, the local API,
enrichment, fixture export, configuration, artifact paths, snapshot runs, and the local review
gate. Root `package.json` scripts are the supported user-facing entry points.

Ordinary builds remain offline apart from their declared live source requirements. Registry
refreshes, RPC enrichment, indexer runs, backfills, and deployment must never become implicit
side effects of deterministic fixture or dbt commands.

## Ownership map

| Script | Responsibility |
| --- | --- |
| [`run_indexer.py`](run_indexer.py) | Launch Envio code generation or development with shared configuration |
| [`run_dbt.py`](run_dbt.py) | Select isolated fixture/live artifacts, bootstrap dbt, and coordinate finalized live snapshots |
| [`snapshot_runs.py`](snapshot_runs.py) | Resolve and record contiguous finalized scan attempts |
| [`run_api.py`](run_api.py) | Bootstrap dependencies and bind FastAPI to loopback |
| [`export_dashboard.py`](export_dashboard.py) | Export bounded fixture JSON atomically |
| [`sync_token_registry.py`](sync_token_registry.py) | Explicitly refresh exact-address registry evidence |
| [`enrich_token_metadata.py`](enrich_token_metadata.py) | Collect pinned-block self-declared token metadata |
| [`enrich_counterparty_types.py`](enrich_counterparty_types.py) | Checkpoint pinned-block bytecode evidence |
| [`project_config.py`](project_config.py) | Resolve shell, ignored YAML, and allowed fallback configuration |
| [`artifact_paths.py`](artifact_paths.py) | Centralize isolated DuckDB artifact locations |
| [`check_dbt_docs.py`](check_dbt_docs.py) | Enforce dbt documentation coverage and ownership metadata |
| [`codex_review_gate.sh`](codex_review_gate.sh) | Run the configured staged-diff pre-commit review |

## Commands

Use the root commands rather than invoking implementation scripts directly:

```sh
bun run indexer:dev
bun run analytics:build:fixture
bun run analytics:build:hyperindex
bun run export:dashboard
bun run tokens:refresh
bun run labels:enrich --limit 100
bun run addresses:enrich
bun run api:dev
```

Networked or potentially expensive commands are explicit:

- `indexer:dev` starts HyperIndex and may index/backfill its configured range.
- `analytics:build:hyperindex` reads live progress/finality and writes a live snapshot attempt.
- `tokens:refresh`, `labels:enrich`, and `addresses:enrich` contact external sources.

Fixture builds and exports are deterministic and must remain isolated from live Postgres and
`live.duckdb`.

## Contracts

- [Operations and exact command procedures](../docs/operations.md)
- [System boundaries and artifact ownership](../ARCHITECTURE.md)
- [Data and local-state contracts](../docs/data-model.md)
- [Configuration examples](../config.example.yaml) and [environment names](../.env.example)

Script changes that affect commands, credentials, enrichment, recovery, or delivery must update
the operations guide in the same change.
