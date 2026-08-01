# Analytics

This component owns reproducible dbt transformations from captured event evidence and explicit
offline enrichment into DuckDB. It preserves exact event identity and raw values, builds one
materialized semantic event relation, and projects purpose-built dashboard marts.

It does not initiate indexing or enrichment during an ordinary build, query RPC at runtime, hide
source provenance, or make token-standard, legitimacy, ownership, or historical-account claims.

## Data paths

| Mode | Input | Artifact | Consumer |
| --- | --- | --- | --- |
| Live | Read-only HyperIndex Postgres plus offline inputs and the ignored account-evidence cache | `artifacts/live.duckdb` | Loopback API |
| Fixture | Checked-in deterministic seeds and an empty typed account-evidence relation | `artifacts/fixture.duckdb` | Tests and bounded static export |

The artifacts are isolated. Fixture validation must never overwrite or serve the live database.
Files under `artifacts/` and generated dbt output under `target/` are local build products, not
hand-edited sources.

## Layout

| Path | Responsibility |
| --- | --- |
| [`models/staging/`](models/staging/) | Normalize source evidence without changing its meaning |
| [`models/intermediate/`](models/intermediate/) | Resolve sourced enrichment and materialize complete semantic events |
| [`models/marts/`](models/marts/) | Delivery-specific tables for the API and fixture exporter |
| [`models/unit_tests.yml`](models/unit_tests.yml) | Deterministic dbt unit contracts |
| [`tests/`](tests/) | Singular grain, reconciliation, inventory, and semantic tests |
| [`seeds/`](seeds/) | Reviewed configuration, fixture facts, registry snapshot, and enrichment inputs |
| [`models/exposures.yml`](models/exposures.yml) | Live API and fixture-export consumers |
| [`docs/data_contracts.md`](docs/data_contracts.md) | Reusable dbt Docs definitions |

## Commands

Run from the repository root:

```sh
bun run analytics:build:fixture
bun run analytics:build:hyperindex
bun run analytics:docs:generate
bun run analytics:docs:serve
bun run test:analytics
```

`test:analytics` tests the already materialized fixture artifact; build the fixture models first.
The fixture build is deterministic. The live build requires HyperIndex progress, a Postgres DSN,
and Ethereum finality evidence, and records attempted intervals in `ops.pipeline_runs`.

## Contracts

- [Model grains, fields, local state, and tests](../docs/data-model.md)
- [Dependency and evidence boundaries](../ARCHITECTURE.md)
- [Build modes, catalog, enrichment, and recovery](../docs/operations.md)
- [Detailed semantic and export policy](../docs/architecture.md)

When a model grain or field changes, update its layer-owned YAML and
[data-model contract](../docs/data-model.md) with the implementation and tests.
