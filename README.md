# EVM Wallet Search

Portfolio-grade Ethereum wallet analytics MVP for one pinned wallet: `vitalik.eth`.

The pipeline indexes wallet-relevant `Transfer(address,address,uint256)` events plus the selected top-level transaction sender and target with Envio HyperIndex and transforms them through dbt into ERC-20-oriented DuckDB marts. The primary product is a locally run React application backed by an API that queries those marts on demand. Transfer `from`, `to`, raw value, and wallet-relative direction remain the event source of truth; transaction envelope fields are separate evidence about initiation and routing.

The source is signature-based, not standards-proof: ERC-721 uses the same `Transfer` signature, and the current wildcard indexer does not disambiguate token standards. Captured rows are therefore ERC-20-intended analytics inputs, not proof that every emitting contract complies with ERC-20.

The local frontend now queries that API. The static JSON path is retained only for a bounded, fixture-backed GitHub Pages portfolio demo; it is not the serving path for complete HyperIndex analytics.

## Wallet

- ENS: `vitalik.eth`
- Pinned address: `0xd8da6bf26964af9d7eed9e03e53415d37aa96045`
- Chain: Ethereum mainnet (`1`)

## Commands

```sh
bun install
python3 -m pip install -r requirements-dev.txt
bun run indexer:dev
bun run analytics:build:hyperindex
bun run api:dev
bun run analytics:build:fixture
bun run labels:sync
bun run labels:enrich --limit 100
bun run addresses:enrich
bun run static:check
bun run test
```

`analytics:build:hyperindex` is the local-product analytics path. It selects the newest block covered by both HyperIndex's transactional progress and Ethereum finality, records the attempted contiguous interval in `ops.pipeline_runs`, reads the case-sensitive `public."Erc20Transfer"` entity table through that finalized bound, and materializes complete marts in `analytics/artifacts/live.duckdb`; see `docs/operations.md`.

`bun run api:dev` starts a loopback-only FastAPI service on `http://127.0.0.1:8000`. In a second terminal, `bun run dashboard:dev` starts the API-backed React app and proxies `/api` to that loopback service. The API opens `analytics/artifacts/live.duckdb`, requires HyperIndex provenance, validates filters, performs exact calculations across every matching row, and returns bounded rankings or cursor-paginated event pages with complete matching counts. Analytics relations remain read-only to the application; manual token-recognition choices are stored in the isolated `app.token_recognition_overrides` table in the same DuckDB file. FastAPI supplies query validation and OpenAPI at `/docs`; no additional persistence service is introduced.

`analytics:build:fixture` (also available as the compatibility alias `analytics:build`), `export:dashboard`, and the production Vite build form the deterministic fixture-demo path used by CI and, eventually, GitHub Pages. Fixture dbt commands write `analytics/artifacts/fixture.duckdb`, clear the live Postgres DSN from their child environment, and never overwrite `analytics/artifacts/live.duckdb`. Only the generated `public/data` JSON belongs to the static demo.

`tokens:refresh` (also available as `labels:sync`) refreshes the checked-in exact-address registry from Trust Wallet, Uniswap, CoinGecko, and qualifying Coinbase Exchange Ethereum assets. `labels:enrich` reads self-declared ERC20 metadata for the highest-impact unverified contracts. `addresses:enrich` batches pinned-block `eth_getCode` observations for every distinct nonzero, nonself event counterparty and checkpoints them in the ignored local evidence database. Ordinary dbt builds never invoke registry or RPC enrichment, and fixture mode contains no invented account evidence.

## Layout

- `indexer/`: Envio HyperIndex config, schema, and handlers for the ERC-20-intended `Transfer` signature.
- `analytics/`: dbt project plus isolated `artifacts/live.duckdb` and `artifacts/fixture.duckdb` outputs.
- `server/`: loopback-only read API for exact, bounded queries over the live DuckDB marts.
- `src/`: React dashboard with isolated live-API and fixture-demo adapters.
- `scripts/`: dbt orchestration, enrichment, and the fixture-demo JSON exporter.
- `config.example.yaml`: shared Envio, Postgres, and Ethereum RPC configuration template; copy it to the git-ignored `config.yaml` for local values.
- `public/data/`: generated fixture-demo JSON for static hosting, not the complete local application database.

## Documentation

- `AGENTS.md`: concise durable instructions, invariants, validation, and change routing for coding agents.
- `ARCHITECTURE.md`: high-level system map, boundaries, dependency direction, and known implementation gaps.
- `docs/architecture.md`: pipeline flow, scope, and documentation update rules.
- `docs/data-model.md`: staging, intermediate, mart grain, and tests.
- `docs/operations.md`: local database mode, fixture-demo mode, setup, and verification.

When code changes a documented behavior or boundary, update the owning context in the same change. Use the routing table in `AGENTS.md`; for example, a mart schema change must update `docs/data-model.md`, `analytics/models/schema.yml` as applicable, `src/data.ts`, and any affected export or dashboard notes.

## GitHub Automation

- CI first runs the fast mandatory static gate—Oxlint and `tsc` for JavaScript/TypeScript,
  Ruff and Pyright for Python—then runs the deterministic fixture-demo pipeline and
  production static build on every pull request and every push to `main`. Its downloadable
  dashboard build is retained for one day; that is artifact storage, not a website expiry time.
- Deploy runs only after successful `main` CI (or a manual dispatch) and only when the repository variable `ENABLE_GITHUB_PAGES` is exactly `true`. The published site remains online until it is replaced or disabled.
- Dependabot checks GitHub Actions, the root JavaScript application, the indexer package, and Python analytics dependencies every Monday.
- The pull-request template makes validation, data-contract, security, documentation, and screenshot checks explicit.
- `.github/copilot-instructions.md` gives GitHub Copilot project-specific review priorities. It guides Copilot when review is requested; it does not approve or merge changes automatically.

GitHub Pages deployment is intentionally gated because private-repository Pages availability depends on the GitHub plan. See `docs/operations.md` for the enablement steps and hosting alternatives.

### Local Codex review gate

Install the repository-managed Git hooks once after cloning:

```sh
bun run hooks:install
```

Every commit with staged changes then starts a fresh, ephemeral Codex session in a read-only sandbox. It reviews only `git diff --cached`, returns a schema-validated result, and blocks the commit only for concrete correctness, security, data-integrity, regression, portability, materially missing-test, or material documentation-drift errors. Documentation drift is blocking only when staged behavior or architecture changes leave the owning context missing, stale, or contradictory; behavior-preserving implementation details do not require mechanical documentation edits. The hook requires authenticated `codex` and `bun` commands and may take longer than deterministic checks because it calls an agent.

Run the same gate without committing with `bun run review:staged`. For an exceptional offline or recovery commit, bypass it once with `SKIP_CODEX_REVIEW=1 git commit ...`; GitHub CI still remains the shared enforcement layer.

## Delivery Contracts

### Local application — primary product

The target local runtime is:

```text
Envio HyperIndex Postgres → dbt → DuckDB → local API → React
```

DuckDB is the application query source. The API verifies the completed finalized run behind the artifact, applies filters, rankings, counts, and pagination on demand against the complete marts, and returns provenance with every response. React calls the API rather than connecting directly to Postgres or receiving database/RPC credentials. Search, recognition, and inclusive account-evidence filters therefore operate on all matching DuckDB rows before the API returns bounded panel data.

The planned Docker distribution will package the local services and persistent data needed by a user who clones the project and runs their own indexer and analytics. Its service and volume contract is not implemented yet.

### GitHub Pages — fixture demo only

The fixture exporter produces five generated files. The current static dashboard loads summaries, timeline rows, events, and metadata; `graph.json` remains only as a legacy export-contract artifact:

- `graph.json`: legacy graph nodes and edges; not loaded by the current dashboard.
- `summaries.json`: token and counterparty summaries.
- `timeline.json`: daily aggregates.
- `events.json`: event-level transfer rows.
- `meta.json`: provenance, complete mart counts, JSON export counts, and export limits.

The demo contract is typed in `src/data.ts` and generated by `scripts/export_dashboard.py` from deterministic fixture marts. Event rows preserve raw Transfer `from_address`/`to_address`, nullable top-level `transaction_from_address`/`transaction_to_address`, sender/target relation evidence, and a nullable indirect marker. Token summaries include confirmed indirect inbound and outbound counts.

`bun run dashboard:build` always selects this static adapter for production/Pages output. `bun run dashboard:dev:fixture` is available for explicitly inspecting the fixture demo locally; it never enables the live API adapter at the same time.

The exporter still contains full-history candidate-union logic for 315 composed filter selections. That machinery belongs only to the legacy fixture-demo contract and must not expand; the local dashboard now computes requested selections through DuckDB-backed API endpoints.

## Dashboard Controls

- Dashboard scope: the product header stays generic and states that the view is based on emitted `Transfer(address,address,uint256)` events. A separate analysis-context panel makes the canonical Ethereum address the primary subject and presents the configured project label as secondary context rather than a live ENS-resolution claim. Fixture mode marks it as an `Example wallet`; HyperIndex mode marks it as the `Configured wallet`.
- Table presentation: column headings retain normal title case rather than being transformed to all capitals.
- Theme toggle: switches palettes in place and stores the preference locally.
- Filter bar: defaults to `All`, offers `Recognized` and `Other`, and applies recognition plus address-type evidence before filtering the timeline, events, token summaries, counterparties, pagination, and summary cards by token, address, direction, or transaction text. Counterparty ranking uses recognition inclusively: an address with both recognition states remains eligible under either relevant selection and keeps its complete in-scope activity count. Hovering or focusing the adjacent information control defines recognition and its limits. Live mode evaluates the selection over complete DuckDB rows; fixture mode evaluates only its bounded demo payload.
- Address type: a two-option multi-select filters every view by user-facing `EOA` or `Contract`. Selecting both means all rows, including unresolved internal RPC failures; `unknown` and EIP-7702 are not separate user controls. The click-open menu closes automatically when the pointer leaves it. Its adjacent hover/focus information control explains that this is pinned-block bytecode evidence rather than permanent identity.
- Data provenance: a shared `Current selection` strip distinguishes fixture from HyperIndex data and shows cumulative `Blocks X–Y · Finalized` coverage backed by completed runs, generation time, and classified versus eligible nonzero/nonself counterparties. Fixture mode says `Coverage not recorded`. The address-evidence hover text separates address-level from event-weighted coverage and discloses failed and not-checked counts. Summary cards stay minimal and are exact for the active live selection; panel labels distinguish returned top-N/page rows from complete matching counts.
- Activity timeline: shares the overview row with Top Counterparties, keeping the time pattern and the ranked addresses visible together. It shows captured Transfer-signature event counts in zero-based stacked inbound/outbound/self UTC bars, with a labeled event-count axis, intermediate scale values, and immediate hover or keyboard-focus details. Self activity is a neutral segment and is never folded into inbound or outbound. `All years` displays the complete observed range as yearly bars. The Year dropdown—or a yearly bar—opens one year's monthly breakdown and filters the live dashboard to that exact UTC year; a monthly bar narrows it to that month, and `Clear month` returns to the year. Returning the dropdown to `All years` removes the time filter. Calendar positions remain stable when other filters change, and the calendar period containing live data generation is marked partial. Fixture mode permits year/month chart navigation but disables dashboard period cross-filtering.
- Etherscan navigation: token symbols and visible emitting-contract addresses open their token page, visible counterparties open their address page, and transaction icons open their transaction page in a new tab.
- Address-type badges: ranked counterparties and recent events show only `EOA` or `Contract`. EOA means no ordinary contract bytecode was observed at the pinned block; the tooltip discloses exact EIP-7702 delegation evidence when present and never claims personhood or permanence. Unresolved failures receive no public type badge.
- Top counterparties: ranks addresses by captured `Transfer(address,address,uint256)` event count, not a proven ERC-20-only count or distinct transaction count. It aggregates matching internal classification rows into one address row and shows emitting-contract breadth plus `Inbound / Outbound Events` counts. The ranking excludes the zero address, the tracked wallet, and addresses observed as emitting token contracts; the underlying event rows remain intact. Inbound/outbound values are Transfer-signature event counts, not token quantities.
- Zero-address handling: excludes the Ethereum zero address from the counterparty ranking because it represents mint/burn mechanics, while retaining those transfers in timeline, event, and token-activity analytics.
- Token activity: occupies the full row immediately below the timeline/counterparty overview and fits all columns without horizontal scrolling at normal desktop widths; narrow screens retain an explicit horizontal overflow fallback. It is a descending captured-event ranking at one row per emitting contract. Each row shows rank, symbol/name, compact exact-address identity, an exact event count with a proportional comparison bar, inbound/outbound/self event counts, exact confirmed-indirect counts, and distinct external counterparties with sender/recipient detail. Sender and recipient mean addresses in emitted token events, not proven people or transaction initiators. Bars encode event frequency only, never token quantity or economic value. Exact raw values remain strings and token-decimals metadata remains available separately, but normalized quantities are intentionally deferred until an exact amount contract has a trustworthy use.
- Direction semantics: recent events are `in`, `out`, or `self`, derived only from emitted `Transfer.from` and `Transfer.to` relative to the tracked wallet. A self-transfer has the wallet on both sides, remains one event, and is excluded from inbound/outbound counts, counterparty totals, and rankings; the timeline presents it only in the neutral self segment.
- Transaction initiation evidence: recent-event `in`/`out` directions gain an asterisk only when the selected top-level transaction sender differs from emitted `Transfer.from`. Token-activity rows show exact indirect inbound/outbound counts. The tooltip explains common causes such as `transferFrom`, routers, Safe/account abstraction, and synthetic event emission; a mismatch alone never proves intent, legitimacy, or economic ownership. Legacy rows without selected transaction fields remain unknown rather than being labeled direct.
- Token classification: presents normal-case `Recognized` and `Other` labels, including normal-case copy in the Recognition information popover. A token is automatically recognized when its exact Ethereum contract address appears in a selected registry; a local manual override can set either result or return to `Automatic`. The Recognition column's hover/focus information control explains these three choices. Live changes persist in the existing DuckDB artifact and can be undone for four seconds. Fixture-demo controls are read-only. Detailed quality evidence remains internal.
- Event pagination: renders 10 events initially, reveals 10 more with Show more, and reverses one page at a time with Show less while keeping the visible and total counts explicit.

Playwright is included as a dev dependency for local rendered-dashboard checks and screenshots.

## Token Labels

`analytics/seeds/token_metadata.csv` is a generated Ethereum-mainnet snapshot from Trust Wallet, Uniswap, CoinGecko, and qualifying online Coinbase Exchange Ethereum contracts. `token_metadata_manifest.json` records upstream URLs, versions, commit SHA, synchronization time, qualification rule, and counts. Run `bun run tokens:refresh` explicitly to replace this snapshot; ordinary builds remain offline. `token_label_overrides.csv` is the reviewed manual layer and takes precedence for corrections.

`token_rpc_metadata.csv` stores pinned-block `name`, `symbol`, and `decimals` responses for unverified contracts. Run `bun run labels:enrich --limit 100` to process the next unlabeled contracts by transfer count, `--retry-failed` to retry failures, or `--refresh` to reread already attempted contracts. RPC metadata never establishes trust, and self-declared names and symbols remain display metadata rather than reputation signals.

`analytics/artifacts/account_evidence.duckdb` is the ignored live evidence cache, with one row per `(chain_id, address)`. Run `bun run addresses:enrich` to process every unresolved distinct nonzero, nonself event counterparty, or use `--limit` only for a deliberate partial run. The command resolves one concrete Ethereum `safe` block, batches `eth_getCode`, checkpoints each batch, retries failures, and never automatically overwrites a successful prior observation. Empty code becomes internal `eoa_candidate`, exact EIP-7702 delegation remains internal code-state evidence under that public EOA presentation, ordinary code becomes `contract`, and unavailable code remains retryable `unknown`. Safe and ERC-4337 evidence are not collected.

Any exact-address registry match produces the automatic `recognized` classification; no match produces `other`. Registry membership is time-varying evidence, not a security guarantee. The lower-level quality tier remains internal. No price, market-cap, volume, or liquidity API is used. Exact definitions and limitations are documented in `docs/architecture.md` and `docs/data-model.md`.
