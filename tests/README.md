# Tests

This directory owns deterministic application, orchestration, enrichment, export, and indexer
contract tests. Tests should prove the closest observable boundary without standing in for
documentation or live HyperIndex verification.

dbt singular tests live in [`analytics/tests/`](../analytics/tests/), and dbt unit tests live in
[`analytics/models/unit_tests.yml`](../analytics/models/unit_tests.yml). Their grains and semantic
expectations are documented in the [data-model contract](../docs/data-model.md#tests).

## Test map

| Area | Files |
| --- | --- |
| Dashboard components and interactions | `dashboard-smoke.test.tsx`, `dashboard-recognition.test.tsx`, `activity-timeline.test.tsx` |
| Dashboard state, formatting, and presentation | `dashboard-model.test.ts`, `dashboard-presentation.test.ts`, `dashboard-fixtures.ts` |
| Live API adapter and delivery types | `dashboard-api.test.ts`, `export-shape.test.ts` |
| Local API behavior | `api_test.py`, `test_run_api.py` |
| Fixture exporter and artifact isolation | `test_dashboard_export.py`, `test_artifact_paths.py` |
| Indexer normalization | `indexer-transfer.test.ts` |
| Snapshot continuity, finality, bounded indexing, raw merge, and worker orchestration | `test_snapshot_runs.py`, `test_run_indexer.py`, `test_wallet_scan_raw.py`, `test_wallet_scan_worker.py` |
| Token registry and RPC metadata | `test_token_registry.py`, `test_rpc_metadata.py` |
| Counterparty bytecode evidence | `test_counterparty_types.py` |
| dbt documentation coverage | `test_dbt_docs.py` |

`dashboard-fixtures.ts` is shared test input, not the generated JSON demo contract under
`public/data/`.

## Commands

Run from the repository root:

```sh
bun run test:js
bun run test:api
bun run test:labels
bun run test:analytics
bun run test
```

- `test:js` runs the Vitest suites.
- `test:api` runs the isolated FastAPI contract suite.
- `test:labels` runs the Python `test_*.py` suites, including enrichment, export, snapshot,
  documentation, and launcher tests.
- `test:analytics` tests the already built fixture artifact; run
  `bun run analytics:build:fixture` first when invoking it separately.
- `test` builds and documents the fixture artifact, runs the Python and JavaScript suites,
  exports fixture JSON, and runs dbt tests.

Fixture validation is deterministic CI/demo coverage. It does not prove live Postgres attachment,
HyperIndex replay behavior, RPC provider behavior, or finalized live coverage.

## Review boundary

Keep tests aligned with the component contracts:

- [Indexer](../indexer/README.md)
- [Analytics](../analytics/README.md)
- [Local API](../server/README.md)
- [Dashboard](../src/README.md)
- [Scripts](../scripts/README.md)

When a test exposes a genuine contract change, update the owning documentation using
[AGENTS.md](../AGENTS.md#change-routing). Do not weaken evidence caveats merely to make a fixture
or assertion easier to express.
