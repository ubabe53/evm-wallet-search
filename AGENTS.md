# AGENTS.md

## Mission

Build a portfolio-grade Ethereum wallet interaction graph whose analytics are reproducible, bounded, and honest about what the ERC-20-intended `Transfer` signature can—and cannot—prove.

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
- One configured wallet, currently the pinned address for `vitalik.eth`.
- One `Transfer(address,address,uint256)` event signature, intended for ERC-20 analytics. ERC-721 uses the same signature, and the current wildcard indexer does not disambiguate standards; never claim every captured row is proven ERC-20.
- HyperIndex Postgres is ingestion persistence; `analytics/artifacts/live.duckdb` is the complete local analytics artifact. Deterministic tests and static-demo export use the separate `analytics/artifacts/fixture.duckdb`.
- The local read-only FastAPI service in `server/` queries only `analytics/artifacts/live.duckdb`; it must reject fixture provenance.
- The React app has two explicit build-time modes: local development queries the live API, while the fixture-demo build reads generated JSON. Do not add a runtime switch that can mix them.
- Static JSON is only the bounded fixture-backed GitHub Pages demo path.

Native ETH transfers, traces, calls, approvals, NFT-specific interpretation/UI, arbitrary wallet lookup, USD prices, and an implemented Docker stack are outside the current MVP. Adding one requires an explicit architecture and data-contract decision.

## Non-negotiable data semantics

- Identity is chain ID plus the canonical identifier. Event identity is `(chain_id, transaction_hash, log_index)`.
- Preserve block/transaction/log identifiers, token address, sender, recipient, timestamp, and exact raw value.
- Store raw token quantities as arbitrary-precision integers or exact strings. Never aggregate quantities across token contracts.
- Define direction relative to the configured wallet and keep self-transfer and zero-address policies explicit.
- A `Transfer` log proves emission, not intent, economic ownership, transaction initiation, standards compliance, or historical account type.
- Token symbols/names, reputation, spam status, and account type are sourced, time-varying enrichment—not identity facts. The configured `vitalik.eth` value is a pinned project label, not a live ENS-resolution claim; any future ENS resolution must record its source and observation time/block.
- Preserve detailed token reputation evidence internally. The dashboard exposes only a default-off `Include spam` toggle; no spam flag is not proof of trust.
- `eoa_candidate` means no bytecode was observed at a pinned block. It does not prove personhood, control, permanence, or EOA history.
- Distinguish complete DuckDB/API results from bounded demo exports. Always carry source, block/time boundaries, generation time, limits, and sampling state.

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
| Model grain, keys, fields, tests, classifications, or exclusions | `docs/data-model.md` and `analytics/models/schema.yml` as applicable |
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
- No repository-wide linter is currently configured.

## Validation

- React/TypeScript: `bunx tsc --noEmit` and `bun run test:js`
- Dashboard presentation/build: `bun run dashboard:build`
- Python/enrichment: `bun run test:labels`
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
bun run test
bun run review:staged
```
