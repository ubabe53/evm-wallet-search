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
| [`run_indexer.py`](run_indexer.py) | Launch Envio code generation/development or one isolated bounded wallet scan with shared configuration |
| [`wallet_scan_worker.py`](wallet_scan_worker.py) | Sequence finalized bounded indexing, shared raw merge/checkpointing, staged dbt, and run completion |
| [`wallet_scan_raw.py`](wallet_scan_raw.py) | Validate Envio progress/finality and transactionally merge canonical raw events into shared Postgres persistence |
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
| [`local_stack.ts`](local_stack.ts) | Build, start, monitor, inspect, and stop the persistent local Compose product |

## Commands

Use the root commands rather than invoking implementation scripts directly:

```sh
bun run indexer:dev
bun run indexer:scan -- --wallet 0x... --from-block 100 --to-block 200 --schema wallet_scan_example
bun run wallet-scan:worker # normally invoked by the API with its WALLET_SCAN_* contract
bun run analytics:build:fixture
bun run analytics:build:hyperindex
bun run export:dashboard
bun run tokens:refresh
bun run labels:enrich --limit 100
bun run addresses:enrich
bun run api:dev
bun run app:up -- 0x...
bun run app:status
bun run app:logs
bun run app:down
```

Networked or potentially expensive commands are explicit:

- `indexer:dev` starts HyperIndex and may index/backfill its configured range.
- `indexer:scan` runs `envio start --restart` for one caller-validated wallet/range inside a
  required temporary `wallet_scan_*` schema. It requires the local Envio services, performs
  network indexing, and resets only that isolated schema; it neither proves finality nor merges or
  publishes the resulting rows by itself.
- `wallet-scan:worker` is the first-party API adapter. It requires the manager-provided
  `WALLET_SCAN_*` job variables plus explicit read/write Postgres credentials, and it may start a
  bounded network index before updating only the supplied staged DuckDB path.
- `analytics:build:hyperindex` reads live progress/finality and writes a live snapshot attempt.
- `tokens:refresh`, `labels:enrich`, and `addresses:enrich` contact external sources.
- `app:up` builds local images and submits a networked finalized wallet scan; it reports ready only
  after atomic live-artifact publication. `app:down` preserves named data volumes.

Fixture builds and exports are deterministic and must remain isolated from live Postgres and
`live.duckdb`.

## Contracts

- [Operations and exact command procedures](../docs/operations.md)
- [System boundaries and artifact ownership](../ARCHITECTURE.md)
- [Data and local-state contracts](../docs/data-model.md)
- [Configuration examples](../config.example.yaml) and [environment names](../.env.example)

Script changes that affect commands, credentials, enrichment, recovery, or delivery must update
the operations guide in the same change.
