# Architecture

This file is the high-level system map for humans and agents. It records what exists now, the intended dependency direction, and the boundaries that changes must preserve. Detailed metric and operational contracts live under `docs/`.

## System at a glance

```text
Ethereum mainnet
      │ Transfer(address,address,uint256) logs involving the configured wallet
      │ (ERC-20-intended; token standard is not disambiguated)
      ▼
Envio HyperIndex
      │ normalized Erc20Transfer entities
      ▼
HyperIndex Postgres (ingestion persistence)
      │ read-only dbt source in live mode
      ▼
dbt + offline token inputs + local account evidence cache
      │ staging → intermediate evidence → marts
      ▼
DuckDB (complete local analytics artifact)
      ├─────────────── local product ───────────────────────┐
      │                                                ▼
      │                                      local FastAPI + recognition overrides
      │                                                │
      │                                                ▼
      │                                         React dashboard
      │
      └── fixture demo exporter → bounded JSON → React/static hosting
```

The frontend selects exactly one path at build time: local development uses bounded, typed, on-demand API queries over DuckDB, while GitHub Pages uses only a small fixture-derived static export.

## Component map

| Component | Location | Responsibility | Must not become |
| --- | --- | --- | --- |
| Indexer | `indexer/` | Capture wallet-relevant `Transfer(address,address,uint256)` logs and persist one normalized entity per log | A claim that every row is proven ERC-20, or a general trace/call/approval/arbitrary-wallet indexer without a scope decision |
| Analytics | `analytics/` | Transform exact event facts and offline enrichment into tested DuckDB marts | A runtime RPC client or a place that hides source/provenance boundaries |
| Orchestration and enrichment | `scripts/` | Run dbt/indexer/API commands, refresh explicit enrichment inputs, and produce the fixture demo export | An implicit network/backfill step during ordinary builds |
| Complete live analytical store | `analytics/artifacts/live.duckdb` | Hold complete HyperIndex-derived analytics plus the application-owned token-recognition override table | A checked-in artifact, browser-delivered database, or general application database |
| Local account evidence store | `analytics/artifacts/account_evidence.duckdb` | Checkpoint one successful pinned bytecode observation per event counterparty, with retryable failures | A checked-in seed, an implicit build-time RPC job, or proof of permanent identity |
| Deterministic demo store | `analytics/artifacts/fixture.duckdb` | Build fixture-only analytics for tests and static export | A source for local live analytics |
| Local API | `server/` | Validate filters, execute exact bounded queries, and mutate only local token-recognition overrides in the live artifact | An ingestion service, general database writer, or fixture-data server |
| Fixture demo contract | `public/data/`, `src/data.ts` | Serve bounded generated JSON only to the explicit fixture/static build | The complete-history local serving architecture |
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
- DuckDB analytics schemas are derived and reproducible; event identity and exact raw values originate upstream and remain preserved. The isolated `app.token_recognition_overrides` table is mutable local product state and is never rewritten by dbt models.
- Enrichment joins onto event facts. It may add sourced interpretation but must not rewrite immutable event evidence.
- User-facing aggregations operate on eligible mart rows and keep token-contract identity in the grain where amounts are involved.
- Generated demo files are downstream artifacts and are never hand-edited.

## Data and trust boundaries

### On-chain evidence

A captured `Transfer(address,address,uint256)` log establishes that a contract emitted that signature with specific indexed participants and a raw third value at a block/log position. It does not establish token standard, intent, transaction initiation, execution path, economic ownership, standards compliance, or whether a label is trustworthy. ERC-721 uses the same event signature; because the current wildcard indexer has no standard-disambiguation step, an ERC-721-like row can enter marts that are currently shaped and named for ERC-20 analytics, with a token ID occupying the raw-value field.

### Enrichment evidence

Token metadata, registry membership, RPC responses, spam reputation, and bytecode observations are sourced and time-varying. Every such enrichment must retain its source plus an observation time/block or version/reason sufficient to audit the derived classification. Safe and ERC-4337-specific collection are intentionally absent; deployed instances fall under ordinary contract-code evidence. The current `vitalik.eth` value is a pinned configured label from `analytics/seeds/wallets.csv`, not evidence of a live ENS resolution; a future resolution workflow must add source and observation provenance before making that claim.

### Delivery boundary

Complete local counts live in DuckDB and are returned by the local API with filters, bounds, limits, and provenance. Static JSON is a bounded fixture demo and must never imply complete live-wallet history.

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
HyperIndex Postgres → dbt live source → `live.duckdb` → FastAPI → React
```

The indexer and live analytics are explicit operations. Builds must not silently start indexing, backfills, registry refreshes, or RPC enrichment.

### Fixture demo path

```text
checked-in fixtures → dbt → DuckDB → bounded JSON exporter → React/static hosting
```

This path is deterministic and suitable for CI and GitHub Pages. It is not proof of live-source integration behavior. Fixture builds write only `analytics/artifacts/fixture.duckdb` and deliberately remove the HyperIndex DSN from dbt's environment. Live builds write only `analytics/artifacts/live.duckdb`; fixture validation cannot overwrite that cache.

## Local API boundary

The loopback-only FastAPI service:

- own DuckDB connections and limit writes to `app.token_recognition_overrides`;
- validates typed query parameters and exposes bounded, paginated queries under `/api/v1`;
- compute filters, counts, rankings, graph pages, event pages, and time ranges on demand;
- return source, generation time, indexed bounds, enrichment coverage, complete matching counts, and returned limits;
- apply manual token-recognition overrides before every filter, count, ranking, graph page, and event page;
- expose `include_spam` as the public reputation control while retaining detailed evidence internally;
- keep secrets and database paths server-side.

The API opens one short-lived DuckDB connection per request rather than sharing a thread-unsafe global connection. It lazily creates the application-owned override table after validating live provenance. The table is keyed by `(chain_id, token_address)` and accepts only `recognized` or `other`; deleting a row restores the automatic registry result. Ranked endpoints return exact calculations ordered over every matching mart row together with `complete_matching_count`, `returned_count`, `limit`, and `is_truncated`. Event pages use an opaque keyset cursor and return `is_paginated`; neither mechanism is sampling. Production mode refuses a fixture-built database. The React API adapter preserves the exact totals, requests bounded graph/token/counterparty results, and follows the opaque event cursor when the user asks for more rows.

## Known implementation gaps

- The static exporter retains legacy candidate-union machinery that should not expand into the local serving model.
- The wildcard `Transfer` source does not yet disambiguate ERC-20 from ERC-721-like contracts that emit the identical signature.
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
