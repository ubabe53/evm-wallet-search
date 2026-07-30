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

Do not add ingestion, general database writes, fixture serving, public binding, or browser-held
credentials without an explicit architecture and data-contract decision.
