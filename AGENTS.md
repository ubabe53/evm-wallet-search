# AGENTS.md

## Mission

Build a portfolio-grade Ethereum wallet transfer analytics application whose results are reproducible, bounded, and honest about what the ERC-20-intended `Transfer` signature can—and cannot—prove.

Optimize for agent legibility: keep architecture, commands, invariants, and change routes explicit enough that a new agent can act safely without reconstructing the repository from scratch.

## Start here

Read only the context needed for the task, in this order:

1. `ARCHITECTURE.md` for the system map, boundaries, dependency direction, and current implementation gaps.
2. The relevant detailed contract:
   - `docs/data-model.md` for grains, keys, fields, classifications, and tests.
   - `docs/operations.md` for setup, commands, credentials, enrichment, recovery, and delivery.
   - `docs/architecture.md` for detailed product behavior, data semantics, and export policy.
3. The implementation and tests nearest the requested change.

Treat documentation as part of the implementation. If code and documentation disagree, verify the behavior from code and tests, then correct the stale context in the same change.

## Current product boundary

- Ethereum mainnet only (`chain_id = 1`).
- One wallet interval is indexed/transformed per run, while the complete live artifact retains every successfully published wallet; the fixed `Example wallet` target is synthetic fixture/demo configuration only and is never a live API fallback.
- One `Transfer(address,address,uint256)` event signature, intended for ERC-20 analytics. ERC-721 uses the same signature, and the current wildcard indexer does not disambiguate standards; never claim every captured row is proven ERC-20.
- HyperIndex Postgres is ingestion persistence: Envio owns normal `public` state, while bounded jobs merge validated canonical events and durable interval checkpoints into the shared `wallet_scan` schema. `analytics/artifacts/live.duckdb` is the complete local analytics artifact and stores one `ops.pipeline_runs` row per attempted finalized snapshot interval. Deterministic tests and static-demo export use the separate `analytics/artifacts/fixture.duckdb`.
- The local read-only FastAPI service in `server/` queries only `analytics/artifacts/live.duckdb`; it must reject fixture provenance.
- The React app has two explicit build-time modes: local development queries the live API, while the fixture-demo build reads generated JSON. Do not add a runtime switch that can mix them.
- Static JSON is only the bounded fixture-backed GitHub Pages demo path. Account-type evidence has no checked-in fixture; fixture builds expose an empty typed relation.

Native ETH transfers, traces, calls, approvals, NFT-specific interpretation/UI, and USD prices are outside the current MVP. The implemented Docker Compose stack is the supported live local distribution path; adding another deployment target requires an explicit architecture and data-contract decision.

## Non-negotiable data semantics

- Identity is chain ID plus the canonical identifier. Event identity is `(chain_id, transaction_hash, log_index)`.
- Preserve block/transaction/log identifiers, token address, sender, recipient, timestamp, and exact raw value.
- Store raw token quantities as arbitrary-precision integers or exact strings. Never aggregate quantities across token contracts.
- Define direction relative to the configured wallet and keep self-transfer and zero-address policies explicit.
- A `Transfer` log proves emission, not intent, economic ownership, transaction initiation, standards compliance, or historical account type.
- Token symbols/names, registry recognition, ENS resolution, and account type are sourced, time-varying enrichment—not identity facts. Live ENS resolution records its resolver source and finalized observation time/block/hash; the configured fixture `Example wallet` value remains only a synthetic pinned project label.
- Do not infer token reputation or legitimacy from names, symbols, registry absence, or wallet-token activity patterns. The dashboard exposes only `All`, `Recognized`, and `Other`: recognition means exact-address registry membership or a manual local override and is not a safety claim.
- `eoa_candidate` means no bytecode was observed at a pinned block. It does not prove personhood, control, permanence, or EOA history.
- Live account evidence is an ignored local DuckDB cache. Successful bytecode observations are not automatically refreshed; failures remain retryable. Do not reintroduce Safe/ERC-4337 RPC collection or a generated account-evidence CSV without a new architecture decision.
- Distinguish complete DuckDB/API results from bounded demo exports. Always carry source, block/time boundaries, generation time, limits, and sampling state.
- Live completeness advances only through contiguous completed runs ending at an Ethereum `finalized` block whose hash is recorded. Event extrema are never a substitute for scan coverage.

## Working method

1. Inspect the nearest implementation, tests, and routed documentation before editing.
2. State and verify assumptions that affect semantics or architecture.
3. Prefer the smallest coherent vertical change over speculative infrastructure.
4. Keep data contracts, code, tests, and documentation synchronized.
5. Run the smallest deterministic checks that can disprove the change.
6. Review the final diff for correctness, unrelated edits, secrets, generated artifacts, and documentation drift.

For difficult or cross-layer work, write or update an execution plan before implementation. A task is done only when behavior, tests, and context agree; passing tests alone do not make stale documentation acceptable.

## Decision routes

- Before changing Web3 metrics, grains, indexing, enrichment, storage, reputation rules, or data contracts, use the `advise-web3-data` skill.
- Before materially changing a dashboard visualization, use `advise-data-visualization`; for Web3 views, use both skills.
- Do not start an expensive indexer run, backfill, RPC enrichment, registry refresh, migration, or deployment unless the user requests it or it is necessary for the requested operation.
- Do not add a dependency, framework, service, or infrastructure layer without explaining the need and tradeoff.

## Change routing

Update the following context in the same change when applicable:

| Change | Required context |
| --- | --- |
| System boundaries, services, dependency direction, or major data flow | `ARCHITECTURE.md` and `docs/architecture.md` |
| Indexing scope, pipeline behavior, ranking, sampling, or semantic policy | `docs/architecture.md` |
| Model grain, keys, fields, tests, classifications, or exclusions | `docs/data-model.md` and the owning dbt YAML under `analytics/models/` or `analytics/seeds/` |
| Setup, credentials, commands, enrichment, deployment, or recovery | `docs/operations.md` and the relevant README section |
| Dashboard controls or visible behavior | README dashboard section and frontend tests |
| Local API contract | server contract, frontend types/tests, `ARCHITECTURE.md`, and `docs/data-model.md` |
| Fixture-demo export schema | exporter, `src/data.ts`, tests, and `docs/data-model.md` |
| Durable agent workflow or repeated review feedback | `AGENTS.md` |

Do not update documentation mechanically when behavior did not change. Do block a change when its behavior or architecture shifted and the relevant source of truth is missing, stale, or contradictory.

## Engineering constraints

- Keep code simple, typed, readable, and consistent with local style.
- Keep secrets out of Git, logs, generated browser data, and examples.
- Update `.env.example` and/or `config.example.yaml` when required configuration changes.
- Do not hand-edit generated JSON or build output; regenerate through repository commands.
- Preserve unrelated changes in a dirty worktree.
- Do not claim a check passed unless that command actually ran.
- Keep mandatory static analysis fast and deterministic: Oxlint for JavaScript/TypeScript,
  Ruff for Python, `tsc` for TypeScript types, and Pyright for Python types.

## Validation

- Static analysis: `bun run static:check`
- React/TypeScript: `bun run typecheck:ts` and `bun run test:js`
- Dashboard presentation/build: `bun run dashboard:build`
- Python/enrichment: `bun run typecheck:py` and `bun run test:labels`
- Local API: `bun run test:api`
- dbt models or seeds: `bun run analytics:build`. Use `bun run test:analytics` only after the relevant models have been built when a separate dbt-test pass is useful; it does not materialize changed SQL.
- Fixture export contract: `bun run export:dashboard` before export-shape tests
- Cross-layer changes: `bun run test`

Fixture validation is deterministic CI/demo coverage, not proof of HyperIndex-specific or live-API behavior.

## Commits and review

Use coherent Conventional Commits. Push only when asked. Let the configured pre-commit Codex review finish and fix blocking findings instead of bypassing it. `SKIP_CODEX_REVIEW=1` is only for an explicitly requested exceptional recovery.

Useful commands:

```sh
bun install
bun run hooks:install
bun run indexer:codegen
bun run indexer:dev
bun run analytics:build
bun run analytics:build:fixture
bun run analytics:build:hyperindex
bun run labels:sync
bun run labels:enrich --limit 100
bun run addresses:enrich --limit 500
bun run export:dashboard
bun run api:dev
bun run dashboard:dev
bun run dashboard:dev:fixture
bun run dashboard:build
bun run static:check
bun run test
bun run review:staged
```
