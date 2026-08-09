# Dashboard

This component owns the React presentation of wallet Transfer-signature analytics. It renders
selection totals, provenance, timeline navigation, token and counterparty rankings, recent
events, recognition controls, and pinned-block account-type evidence.

In live mode, completed-wallet selection belongs to the persistent analysis context and only changes
the wallet-scoped API query. The separate scan launcher creates finalized scan jobs for new or
incomplete targets, clears accepted input, keeps progress visible in the launcher, and switches to a
successfully published wallet automatically. Wallet refreshes keep the last successful wallet and
its provenance visible until the replacement query succeeds; transient failures stay inline and can
be retried without returning to the startup error screen.

The frontend has two explicit build-time data modes:

- `api`: local development calls the loopback API over complete live DuckDB analytics.
- `static`: fixture development and production builds read bounded generated JSON.

There is no runtime switch between them. Browser code must not connect to Postgres, DuckDB, or
Ethereum RPC and must not receive their credentials.

## Important files

| Path | Responsibility |
| --- | --- |
| [`App.tsx`](App.tsx) | Product shell, filters, provenance, and panel composition |
| [`data.ts`](data.ts) | Shared delivery types plus isolated live/static adapters |
| [`dashboard/useDashboard.ts`](dashboard/useDashboard.ts) | Selection state, requests, pagination, and override actions |
| [`dashboard/model.ts`](dashboard/model.ts) | Pure dashboard semantics, formatting, filtering, and aggregation helpers |
| [`dashboard/`](dashboard/) | Timeline, token, counterparty, event, and shared presentation components |
| [`styles.css`](styles.css) | Responsive layout, themes, tables, and interaction styling |
| [`../tests/`](../tests/) | UI, model, API-adapter, accessibility, and presentation contracts |

## Commands

Run from the repository root.

Live mode, after building analytics and starting the API:

```sh
bun run dashboard:dev
```

Deterministic fixture mode:

```sh
bun run analytics:build:fixture
bun run export:dashboard
bun run dashboard:dev:fixture
```

Validation:

```sh
bun run typecheck:ts
bun run test:js
bun run dashboard:build
```

`dashboard:build` always selects the static fixture adapter. Generated files under
`public/data/` are exporter output and must not be hand-edited.

## Contracts

- [Visible dashboard behavior](../docs/architecture.md#dashboard-behavior)
- [API and fixture delivery shapes](../docs/data-model.md#local-api-contract)
- [Fixture export operation](../docs/operations.md#fixture-demo-export)
- [Screenshot placement and verification](../docs/images/README.md)

UI copy must continue to distinguish emitted event evidence from intent, ownership, legitimacy,
standards compliance, and permanent account identity.
