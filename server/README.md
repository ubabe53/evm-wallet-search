# Local API

This component owns the loopback-only FastAPI boundary between complete live DuckDB analytics and
the React dashboard. It validates typed filters, performs exact calculations before applying
presentation limits, and returns provenance, complete matching counts, bounded rankings, and
cursor-paginated events.

Production mode opens only `analytics/artifacts/live.duckdb` and rejects fixture provenance or
inconsistent finalized-run metadata. Analytics relations are read-only to the application. The
only mutable state is the isolated `app.token_recognition_overrides` table in the same local
artifact.

## Important files

| File | Responsibility |
| --- | --- |
| [`app.py`](app.py) | FastAPI application, parameter validation, routes, and response entry points |
| [`queries.py`](queries.py) | DuckDB provenance checks, filters, exact aggregates, ranking, pagination, and override storage |
| [`../scripts/run_api.py`](../scripts/run_api.py) | Dependency bootstrap and loopback server launcher |
| [`../tests/api_test.py`](../tests/api_test.py) | API behavior and response contract |
| [`../tests/test_run_api.py`](../tests/test_run_api.py) | Launcher behavior |
| [`ens.py`](ens.py) | Address/ENS normalization, finalized-block resolution, and scan-input provenance |

## Commands

After a successful live analytics build, run from the repository root:

```sh
bun run api:dev
bun run test:api
```

The service binds to `127.0.0.1:8000`, exposes readiness at `/api/v1/health`, and serves OpenAPI
documentation at `/docs`. Stop it before rebuilding `live.duckdb`, then restart it and reload the
dashboard after the build completes.

## Contracts

- [Local API data contract](../docs/data-model.md#local-api-contract)
- [Application behavior and filter semantics](../docs/architecture.md#local-application-contract)
- [Runtime and recovery procedure](../docs/operations.md#local-setup)
- [System delivery boundary](../ARCHITECTURE.md#local-api-boundary)

## Scan input boundary

`server.ens.resolve_scan_input` accepts a `0x` address or a conservative ASCII ENS name. ENS names
are resolved through the pinned Ethereum mainnet ENS registry and its returned resolver using
`eth_call` at one `finalized` block. The result is a typed `ResolvedScanInput`; callers must carry
it into `ops.pipeline_runs` before starting a scan. An unrecognized or unsupported name raises
`ENSNotRecognizedError` and has no resolved index target. This boundary does not start an indexer,
reindex history, or expose an HTTP dashboard route.

### Scan jobs

Live mode also exposes `POST /api/v1/scan-jobs`, `GET /api/v1/scan-jobs/{job_id}`, and `GET /api/v1/wallets`. These are local orchestration endpoints only. The scan manager enforces one worker, block-0-to-finalized bounds, staging output, and atomic artifact replacement. Fixture mode has no scan controls. `server/scan_jobs.py` is the stable adapter boundary for the future multi-wallet indexer and ENS resolver.

Do not add ingestion, general database writes, fixture serving, public binding, or browser-held
credentials without an explicit architecture and data-contract decision.
