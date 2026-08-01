# Architecture

This file is the high-level system map for humans and agents. It records what exists now, the intended dependency direction, and the boundaries that changes must preserve. Detailed metric and operational contracts live under `docs/`.

## System at a glance

```text
Ethereum mainnet
      │ Transfer(address,address,uint256) logs involving configured wallet targets
      │ (ERC-20-intended; token standard is not disambiguated)
      ▼
address/ENS input → server-side finalized ENS resolver
      │ provenance carried through the scan-job adapter to the worker
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
| Complete live analytical store | `analytics/artifacts/live.duckdb` | Hold additive HyperIndex-derived analytics for all completed wallets, durable wallet targets, wallet-scoped finalized scan generations, wallet-grained snapshot-run history, shared enrichment projections, and the application-owned token-recognition override table | A checked-in artifact, browser-delivered database, or general application database |
| Local account evidence store | `analytics/artifacts/account_evidence.duckdb` | Checkpoint one successful pinned bytecode observation per event counterparty, with retryable failures | A checked-in seed, an implicit build-time RPC job, or proof of permanent identity |
| Deterministic demo store | `analytics/artifacts/fixture.duckdb` | Build fixture-only analytics for tests and static export | A source for local live analytics |
| Local API | `server/` | Validate filters, execute exact bounded queries, and mutate only local token-recognition overrides in the live artifact | An ingestion service, general database writer, or fixture-data server |
| Fixture demo contract | `public/data/`, `src/data.ts` | Serve bounded generated JSON only to the explicit fixture/static build | The complete-history local serving architecture |
| Dashboard | `src/` | Present activity timeline, summary, rankings, provenance, and event views | A direct Postgres, DuckDB, RPC, or secret-bearing client |
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
- DuckDB analytics schemas are derived and reproducible; event identity and exact raw values originate upstream and remain preserved. Orchestration owns `ops.pipeline_runs`, while the isolated `app.token_recognition_overrides` table is mutable local product state; dbt models rewrite neither schema.
- Enrichment joins onto event facts. It may add sourced interpretation but must not rewrite immutable event evidence.
- `int_wallet_transfer_events` is the shared, materialized semantic event relation. It keeps the
  complete row-level evidence inside the standalone DuckDB artifact after build-time source
  attachments are gone. Dashboard marts are independent,
  purpose-built projections from that relation; one serving mart must not become the accidental source
  of fields needed by every other mart.
- User-facing aggregations operate on eligible semantic event rows and keep token-contract identity
  in the grain where amounts are involved.
- Generated demo files are downstream artifacts and are never hand-edited.

## Data and trust boundaries

### On-chain evidence

A captured `Transfer(address,address,uint256)` log establishes that a contract emitted that signature with specific indexed participants and a raw third value at a block/log position. It does not establish token standard, intent, transaction initiation, execution path, economic ownership, standards compliance, or whether a label is trustworthy. ERC-721 uses the same event signature; because the current wildcard indexer has no standard-disambiguation step, an ERC-721-like row can enter marts that are currently shaped and named for ERC-20 analytics, with a token ID occupying the raw-value field.

### Enrichment evidence

Token metadata, registry membership, RPC responses, ENS resolution, and bytecode observations are sourced and time-varying. Every such enrichment must retain its source plus an observation time/block or version/reason sufficient to audit the derived classification. Safe and ERC-4337-specific collection are intentionally absent; deployed instances fall under ordinary contract-code evidence. The current `vitalik.eth` value remains a configured presentation label, while an explicit live build or scan job resolves an ENS-shaped label at one finalized block and records its source and observation provenance through the selected wallet's run/worker contract. Non-ENS labels use the canonical configured address as direct-input provenance.

### Delivery boundary

Complete local counts live in DuckDB and are returned by the local API with filters, bounds, limits, and provenance. Static JSON is a bounded fixture demo and must never imply complete live-wallet history.

## Stable invariants

- Ethereum mainnet only; identity always includes `chain_id`.
- Stable event key: `(chain_id, transaction_hash, log_index)`; captured block hashes remain adjacent canonical-block evidence rather than becoming identity.
- Raw quantities remain arbitrary-precision integers or exact strings.
- Token-decimals metadata remains separate from exact raw values; the current serving contract does not materialize floating-point normalized amounts.
- Quantities from different token contracts are never summed as if fungible.
- Zero-address mint/burn semantics and self-transfer policy remain explicit. A log whose emitted `from` and `to` both equal the tracked wallet has direction `self`; it remains one event but is neither inbound, outbound, nor an external counterparty interaction.
- Token and account labels are evidence, not canonical identity.
- No-code-at-block means `eoa_candidate`, not proven EOA/personhood/control.
- Account-evidence coverage is measured against the current snapshot's distinct nonzero, nonself event counterparties. Classified, failed, and not-checked address and event counts must reconcile to that population; cached rows outside it do not count.
- Live completeness is a contiguous range of completed snapshot runs from the configured HyperIndex start through an Ethereum `finalized` block; event-bearing block extrema do not establish that range.
- Scan jobs accept only a normalized Ethereum address or a safely normalized ENS name. ENS resolution uses the pinned mainnet registry dependency at a finalized block; the typed observation is handed to the explicit worker adapter, which owns persistence of the original input, normalized name, resolved address, resolver source, block number/hash, and observation timestamp in the selected wallet's output artifact. Unresolved names never enter indexing.
- `pipeline_metadata` keeps cumulative scan bounds separate from observed event block/time extrema and reconciles its complete event count with the semantic and delivery event relations.
- Token names, symbols, and wallet-token activity patterns are never scored as reputation or legitimacy evidence; the public token labels are only `Recognized` and `Other`.
- Bounded outputs disclose their complete matching count, returned count, limits, provenance, and sampling state where applicable.

Detailed field grains and tests are in `docs/data-model.md`.

## Runtime paths

### Local analytics path

```text
address/ENS input → server-side finalized ENS resolver → explicit scan-worker adapter → HyperIndex progress + Ethereum finalized block → dbt live source → `live.duckdb` → FastAPI → React

The scan manager does not interpret ENS provenance or implement the indexer. It copies the complete
live artifact into a temporary staging path and gives that path to the explicit worker adapter. The
worker receives the typed finalized observation and must update the selected wallet's missing range
in place, preserving every existing wallet and shared enrichment cache row. The manager validates
the result and atomically publishes it; this is the publication boundary, not a claim that the
manager itself can collect or merge chain data.
```

The indexer and live analytics are explicit operations. A live build chooses the newest block that is both within HyperIndex's transactional progress and no newer than Ethereum's `finalized` head, selects one wallet through `EVM_WALLET_SCAN_ADDRESS`, records one attempted wallet-scoped interval in `ops.pipeline_runs` and `ops.scan_generations` for that wallet, and advances coverage only after dbt succeeds. A new selected wallet starts at the configured start block; an existing selected wallet starts at its own latest completed block plus one. The complete live DuckDB artifact is additive: publishing a selected wallet must preserve prior wallet projections. Token RPC metadata is cached once per `(chain_id, token_address)` and counterparty bytecode evidence once per `(chain_id, address)`; new wallets reuse successful observations and only add missing candidates. Builds must not silently start indexing, backfills, registry refreshes, or enrichment jobs.

### Fixture demo path

```text
checked-in fixtures → dbt → DuckDB → bounded JSON exporter → React/static hosting
```

This path is deterministic and suitable for CI and GitHub Pages. It is not proof of live-source integration behavior. Fixture builds write only `analytics/artifacts/fixture.duckdb` and deliberately remove the HyperIndex DSN from dbt's environment. Live builds write only `analytics/artifacts/live.duckdb`; fixture validation cannot overwrite that cache.

## Local API boundary


The loopback-only FastAPI service:

- own DuckDB connections and limit writes to `app.token_recognition_overrides`;
- validates typed query parameters and exposes bounded, paginated queries under `/api/v1`;
- compute filters, counts, rankings, timeline buckets, event pages, and time ranges on demand;
- return source, generation time, cumulative indexed bounds, observed event block/time extrema, population-reconciled account-evidence coverage, complete matching counts, and returned limits;
- expose only the event identity, display, classification, and count fields consumed by the dashboard while retaining exact raw values, token decimals, and detailed provenance in the complete DuckDB intermediate relation;
- return self-transfers as the explicit `self` event direction while excluding the tracked wallet from counterparty counts;
- verify that live metadata references the latest completed finalized snapshot run, that completed intervals are contiguous, and that their cumulative event counts reconcile with the analytics snapshot before serving it;
- apply manual token-recognition overrides before every filter, count, ranking, timeline bucket, and event page;
- expose only `recognition=all|recognized|other` as the public token-classification control while retaining factual source evidence internally;
- treat recognition as inclusive counterparty-cohort membership for counterparty rankings, then rank eligible addresses by their complete activity inside the remaining account/search/time scope;
- keep secrets and database paths server-side.

The API opens one short-lived DuckDB connection per request rather than sharing a thread-unsafe global connection. It resolves an omitted wallet from request-time `EVM_WALLET_SCAN_ADDRESS` or the artifact's sole current metadata row; zero or multiple metadata wallets fail clearly and require the selector. It exposes an explicit `dashboard-api-v16` metadata projection instead of forwarding the internal mart with `select *`, then lazily creates the application-owned override table after validating live provenance. The table is keyed by `(chain_id, token_address)` and accepts only `recognized` or `other`; deleting a row restores the automatic registry result. Ranked endpoints return exact calculations ordered over every matching mart row together with `complete_matching_count`, `returned_count`, `limit`, and `is_truncated`. Event pages use an opaque keyset cursor and return `is_paginated`; neither mechanism is sampling. Production mode refuses a fixture-built database. The React API adapter preserves exact totals, requests a stable yearly overview or one selected year's monthly buckets plus bounded token/counterparty rows, applies selected year/month UTC periods through half-open API filters, follows the opaque event cursor, and offers a four-second undo that restores the exact prior override.

## Known implementation gaps

- The static exporter retains legacy candidate-union machinery that should not expand into the local serving model.
- The wildcard `Transfer` source does not yet disambiguate ERC-20 from ERC-721-like contracts that emit the identical signature.
- Docker packaging is an approved direction, but service topology, volumes, health checks, secrets, and startup order are not designed or implemented.

These are explicit gaps, not permissions to fill them opportunistically during unrelated work.

## Context ownership

- `AGENTS.md`: concise durable workflow, invariants, validation, and routing instructions.
- `ARCHITECTURE.md`: high-level component map, boundaries, dependency direction, and known gaps.
- `docs/architecture.md`: detailed product behavior, semantic policy, timeline behavior, classification, and export policy.
- `docs/data-model.md`: model grains, fields, keys, classifications, provenance, and tests.
- `docs/operations.md`: setup, commands, credentials, enrichment, recovery, and delivery procedures.
- `README.md`: user-facing overview, quickstart, and visible dashboard behavior.

When implementation changes one of these truths, update the owning document in the same change. The pre-commit review treats material documentation drift or contradiction as a correctness failure.
