# Architecture

This file is the high-level system map for humans and agents. It records what exists now, the intended dependency direction, and the boundaries that changes must preserve. Detailed metric and operational contracts live under `docs/`.

## System at a glance

```text
Ethereum mainnet
      │ ERC-20 Transfer logs involving the configured wallet
      ▼
Envio HyperIndex
      │ normalized Erc20Transfer entities
      ▼
HyperIndex Postgres (ingestion persistence)
      │ read-only dbt source in live mode
      ▼
dbt + offline enrichment inputs
      │ staging → intermediate evidence → marts
      ▼
DuckDB (complete local analytics artifact)
      ├──────────── intended local product ────────────┐
      │                                                ▼
      │                                      local read-only API
      │                                      (not implemented)
      │                                                │
      │                                                ▼
      │                                         React dashboard
      │
      └── transitional/demo exporter → bounded JSON → React dashboard
```

The current frontend uses the JSON path. The target local application replaces that serving path with bounded, typed, on-demand API queries over DuckDB. GitHub Pages continues to use only a small fixture-derived static export.

## Component map

| Component | Location | Responsibility | Must not become |
| --- | --- | --- | --- |
| Indexer | `indexer/` | Capture wallet-relevant ERC-20 `Transfer` logs and persist one normalized entity per log | A general trace, call, approval, NFT, or arbitrary-wallet indexer without a scope decision |
| Analytics | `analytics/` | Transform exact event facts and offline enrichment into tested DuckDB marts | A runtime RPC client or a place that hides source/provenance boundaries |
| Orchestration and enrichment | `scripts/` | Run dbt/indexer commands, refresh explicit enrichment inputs, and produce the fixture demo export | An implicit network/backfill step during ordinary builds |
| Complete analytical store | `analytics/wallet_analytics.duckdb` | Hold complete locally transformed analytics | A checked-in artifact or a browser-delivered database |
| Transitional/demo contract | `public/data/`, `src/data.ts` | Serve bounded generated JSON to the current frontend and fixture demo | The long-term complete-history serving architecture |
| Dashboard | `src/` | Present graph, summary, provenance, and event views | A direct Postgres, DuckDB, RPC, or secret-bearing client |
| Tests | `tests/`, `analytics/tests/`, `analytics/models/unit_tests.yml` | Enforce UI, export, enrichment, grain, and semantic contracts | A substitute for documenting system intent and boundaries |
| Context layer | `AGENTS.md`, this file, `README.md`, `docs/` | Make constraints, decisions, operations, and change routes legible | Stale narrative that contradicts executable behavior |

## Dependency direction

Dependencies flow inward from evidence collection to transformation to bounded delivery:

```text
indexer entities → dbt sources/staging → evidence models → marts → API/export contract → UI
```

Rules:

- The browser never receives Postgres/RPC credentials or direct database access.
- HyperIndex Postgres is the ingestion source, not the application query interface.
- DuckDB is derived and reproducible; event identity and exact raw values originate upstream and remain preserved.
- Enrichment joins onto event facts. It may add sourced interpretation but must not rewrite immutable event evidence.
- User-facing aggregations operate on eligible mart rows and keep token-contract identity in the grain where amounts are involved.
- Generated demo files are downstream artifacts and are never hand-edited.

## Data and trust boundaries

### On-chain evidence

An ERC-20 `Transfer` log establishes that a contract emitted the event with specific indexed participants and a raw value at a block/log position. It does not establish intent, transaction initiation, execution path, economic ownership, standards compliance, or whether a label is trustworthy.

### Enrichment evidence

Token metadata, registry membership, RPC responses, spam reputation, bytecode observations, Safe evidence, and ERC-4337 observations are sourced and time-varying. Every such enrichment must retain its source plus an observation time/block or version/reason sufficient to audit the derived classification. The current `vitalik.eth` value is a pinned configured label from `analytics/seeds/wallets.csv`, not evidence of a live ENS resolution; a future resolution workflow must add source and observation provenance before making that claim.

### Delivery boundary

Complete local counts live in DuckDB and, once implemented, are returned by the local API with filters, bounds, limits, and provenance. Static JSON is a bounded fixture demo and must never imply complete live-wallet history.

## Stable invariants

- Ethereum mainnet only; identity always includes `chain_id`.
- Stable event key: `(chain_id, transaction_hash, log_index)`.
- Raw quantities remain arbitrary-precision integers or exact strings.
- Quantities from different token contracts are never summed as if fungible.
- Zero-address mint/burn semantics and self-transfer policy remain explicit.
- Token and account labels are evidence, not canonical identity.
- No-code-at-block means `eoa_candidate`, not proven EOA/personhood/control.
- Suspected and reviewed spam remain distinct internally but project to one user-facing `Spam` state.
- Bounded outputs disclose their complete matching count, returned count, limits, provenance, and sampling state where applicable.

Detailed field grains and tests are in `docs/data-model.md`.

## Runtime paths

### Local analytics path

```text
HyperIndex Postgres → dbt live source → DuckDB → local API (planned) → React
```

The indexer and live analytics are explicit operations. Builds must not silently start indexing, backfills, registry refreshes, or RPC enrichment.

### Fixture demo path

```text
checked-in fixtures → dbt → DuckDB → bounded JSON exporter → React/static hosting
```

This path is deterministic and suitable for CI and GitHub Pages. It is not proof of live-source integration behavior. Fixture and live outputs currently share paths; avoid running fixture commands when preserving a live DuckDB cache matters until those artifacts are separated.

## Intended local API boundary

The API is not implemented. When added, it should:

- own read-only DuckDB connections;
- expose typed, bounded, paginated queries;
- compute filters, counts, rankings, graph pages, event pages, and time ranges on demand;
- return source, generation time, indexed bounds, enrichment coverage, complete matching counts, and returned limits;
- expose `include_spam` as the public reputation control while retaining detailed evidence internally;
- keep secrets and database paths server-side.

Adding the API requires updating this file, `docs/data-model.md`, operations documentation, frontend client types, and focused server/client contract tests together.

## Known implementation gaps

- The local DuckDB API does not exist yet.
- React still loads generated JSON.
- The static exporter retains legacy candidate-union machinery that should not expand into the local serving model.
- Fixture and live dbt builds share the DuckDB output path.
- Docker packaging is an approved direction, but service topology, volumes, health checks, secrets, and startup order are not designed or implemented.

These are explicit gaps, not permissions to fill them opportunistically during unrelated work.

## Context ownership

- `AGENTS.md`: concise durable workflow, invariants, validation, and routing instructions.
- `ARCHITECTURE.md`: high-level component map, boundaries, dependency direction, and known gaps.
- `docs/architecture.md`: detailed product behavior, semantic policy, graph behavior, classification, and export policy.
- `docs/data-model.md`: model grains, fields, keys, classifications, provenance, and tests.
- `docs/operations.md`: setup, commands, credentials, enrichment, recovery, and delivery procedures.
- `README.md`: user-facing overview, quickstart, and visible dashboard behavior.

When implementation changes one of these truths, update the owning document in the same change. The pre-commit review treats material documentation drift or contradiction as a correctness failure.
