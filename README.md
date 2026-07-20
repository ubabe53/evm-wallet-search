# EVM Wallet Search

Portfolio-grade Ethereum wallet analytics MVP for one pinned wallet: `vitalik.eth`.

The pipeline indexes ERC20 `Transfer` events plus the selected top-level transaction sender and target with Envio HyperIndex, transforms wallet-relevant transfers through dbt into DuckDB marts, exports static JSON, and serves a React dashboard. Transfer `from`, `to`, raw value, and wallet-relative direction remain the event source of truth; transaction envelope fields are separate evidence about initiation and routing.

## Wallet

- ENS: `vitalik.eth`
- Pinned address: `0xd8da6bf26964af9d7eed9e03e53415d37aa96045`
- Chain: Ethereum mainnet (`1`)

## Commands

```sh
bun install
bun run indexer:dev
bun run analytics:build
bun run analytics:build:hyperindex
bun run labels:sync
bun run labels:enrich --limit 100
bun run addresses:enrich --limit 500
bun run export:dashboard
bun run dashboard:dev
bun run test
```

`analytics:build` defaults to the checked-in 90-day Vitalik snapshot, so the dashboard has realistic data without requiring Postgres. `analytics:build:semantic-fixture` retains the six documented edge-case transfers used by CI and deterministic semantic tests. The dashboard labels snapshot, semantic-fixture, and live HyperIndex provenance explicitly. `analytics:build:hyperindex` reads the case-sensitive `public."Erc20Transfer"` entity table after attaching Envio Postgres read-only through `DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN`; see `docs/operations.md`.

`labels:sync` refreshes the checked-in metadata registry from Trust Wallet, Uniswap, and CoinGecko. `labels:enrich` reads self-declared ERC20 metadata for the highest-impact unverified contracts. `addresses:enrich` collects pinned-block bytecode, Safe, and canonical ERC-4337 EntryPoint evidence for high-activity counterparties. Ordinary dbt builds remain offline and reproducible; no full live account enrichment is part of the fixture path.

## Layout

- `indexer/`: Envio HyperIndex config, schema, and handlers for ERC20 transfers.
- `analytics/`: dbt + DuckDB project with staged, intermediate, and mart models.
- `src/`: React dashboard.
- `scripts/`: dbt orchestration and JSON export.
- `config.example.yaml`: shared Envio, Postgres, and Ethereum RPC configuration template; copy it to the git-ignored `config.yaml` for local values.
- `public/data/`: generated dashboard JSON.

## Documentation

- `docs/architecture.md`: pipeline flow, scope, and documentation update rules.
- `docs/data-model.md`: staging, intermediate, mart grain, and tests.
- `docs/operations.md`: setup, fixture mode, HyperIndex mode, export, and verification.

When code changes, update the related docs in the same change. For example, a mart schema change must update `docs/data-model.md`, `src/data.ts`, and any affected export or dashboard notes.

## GitHub Automation

- CI runs the complete fixture pipeline and production build on every pull request and every push to `main`. Its downloadable dashboard build is retained for one day; that is artifact storage, not a website expiry time.
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

Every commit with staged changes then starts a fresh, ephemeral Codex session in a read-only sandbox. It reviews only `git diff --cached`, returns a schema-validated result, and blocks the commit only for concrete correctness, security, data-integrity, regression, portability, or materially missing-test errors. The hook requires authenticated `codex` and `bun` commands and may take longer than deterministic checks because it calls an agent.

Run the same gate without committing with `bun run review:staged`. For an exceptional offline or recovery commit, bypass it once with `SKIP_CODEX_REVIEW=1 git commit ...`; GitHub CI still remains the shared enforcement layer.

## Data Contract

The dashboard consumes five generated files:

- `graph.json`: Cytoscape nodes and edges.
- `summaries.json`: token and counterparty summaries.
- `timeline.json`: daily aggregates.
- `events.json`: event-level transfer rows.
- `meta.json`: provenance, complete mart counts, JSON export counts, and export limits.

The contract is typed in `src/data.ts` and generated by `scripts/export_dashboard.py`. Event rows preserve raw Transfer `from_address`/`to_address`, nullable top-level `transaction_from_address`/`transaction_to_address`, sender/target relation evidence, and a nullable indirect marker. Token summaries include confirmed indirect inbound and outbound counts.
DuckDB remains the complete analytics artifact. Events, graph interactions, and daily rows are deterministically bounded by status, quality, and exact account-evidence signature. Token and counterparty exports instead preserve candidate unions that prove exact top-500 token and top-50 counterparty rankings for every one of the 6,615 selections formed by 15 non-empty status combinations, 7 non-empty quality combinations, and 63 non-empty inclusive account-filter combinations. The browser aggregates matching token and timeline account cells back to their displayed grains before ranking or rendering. `meta.json` records complete/exported counts, limits, selection counts, exact-ranking guarantees, and `is_sampled`; exact candidate-union rankings remain valid even when other browser exports are sampled.

## Dashboard Controls

- Theme toggle: switches palettes in place, preserves graph positions and viewport state, and stores the preference locally. Graph labels use dark text in light mode and light text in dark mode.
- Filter bar: applies status AND quality AND inclusive account evidence before filtering events, token summaries, graph elements, timeline rows, counterparties, pagination, and summary cards by token, address, direction, or transaction text.
- Account evidence: a six-option multi-select filters the graph, ranked counterparties, and recent events by `EOA candidate`, `Delegated EOA`, `Safe`, `ERC-4337`, `Contract`, or `Unknown`. Safe and ERC-4337 are independent evidence predicates, so an address observed as both remains visible when either corresponding filter is selected.
- Data provenance: distinguishes the fixed Vitalik snapshot, semantic fixture, and HyperIndex data; shows the event block range and complete indexed transfer count; and identifies when recent events are a bounded export.
- Graph density: shows the 25 highest-ranked interactions by default, with controls for 10, 25, 50, or 100 direct wallet-address links. Nodes without a displayed edge are removed automatically.
- Graph activity sizing: interacted-address nodes scale gradually from 26px at one transfer to 68px at 10,000 or more, using their complete ERC20 transfer count with the configured wallet. The fixed logarithmic scale keeps node sizes stable when filters or graph limits change.
- Graph interaction styling: uses a terminal-inspired network canvas with thin weighted links. Token symbols appear on links instead of occupying separate graph nodes. Counterparty labels name independent Safe and ERC-4337 evidence, Safe changes node shape/border weight, and ERC-4337 uses a dotted border, so overlap remains visible without color alone. Hovering a node emphasizes its immediate neighborhood; hovering a link emphasizes that interaction.
- Graph edge labels: show the token symbol and the number of transfers aggregated into that counterparty-token-direction interaction, such as `USDC x5`.
- Etherscan navigation: token symbols open their contract page, visible addresses open their address page, and transaction icons open their transaction page in a new tab. In the graph, clicking a wallet/counterparty node opens its address and clicking an interaction edge opens its token contract.
- Account evidence badges: graph labels, ranked counterparties, and recent events show a primary pinned-block account type. `EOA candidate` means no bytecode was observed and never claims personhood or permanent EOA status. `Delegated EOA` requires code exactly equal to `0xef0100` plus a 20-byte target. Safe badges include the observed threshold as “M/N addresses”; ERC-4337 badges mean the address appeared as `UserOperationEvent.sender` at a versioned canonical EntryPoint within deployment-clamped successful coverage. Failed log chunks remain explicit partial evidence.
- Top ERC-20 counterparties: ranks addresses by ERC20 `Transfer` event count, not distinct transaction count. It aggregates selected status-quality rows into one address row and shows token breadth plus `Amount In / Out` event counts. The ranking excludes the zero address, the tracked wallet, and addresses observed as token contracts; the underlying event rows remain intact. Despite the compact label, In/Out values are transfer-event counts, not token quantities.
- Zero-address handling: excludes the Ethereum zero address from the interaction graph and counterparty ranking because it represents mint/burn mechanics, while retaining those transfers in event and token-flow analytics.
- Graph reset: recenters the graph after pan/zoom. Zoom bounds are derived from the fitted graph size, while hard safety caps prevent unusable extremes. Pan movement is clamped so the graph stays near the viewport.
- Graph theater mode: expands the interaction graph over the dashboard for focused exploration, refits Cytoscape to the larger viewport, locks background scrolling, and exits through the collapse control or Escape.
- Token flow: appears below recent events at one row per token. It shows total transfers, distinct non-zero/non-self `Senders | Recipients`, and the distinct union of those counterparties. Sender and recipient mean addresses in emitted token events, not proven people or transaction initiators. Decimal and exact raw totals remain in the generated data but are intentionally not presented until the amount visualization has a trustworthy use.
- Transaction initiation evidence: recent-event directions gain an asterisk only when the selected top-level transaction sender differs from emitted `Transfer.from`. Token-flow rows show exact indirect inbound/outbound counts. The tooltip explains common causes such as `transferFrom`, routers, Safe/account abstraction, and synthetic or spam event emission; a mismatch alone never proves spam, intent, or economic ownership. Legacy rows without selected transaction fields remain unknown rather than being labeled direct.
- Token classification: displays status separately from `high confidence`, `listed`, or `unknown` quality. Status precedence is reviewed spam, automated suspected spam, high-confidence trusted, then unverified. Trusted and unverified statuses remain selected by default; quality defaults to high confidence, with listed and unknown discoverable in the Quality menu. Hover titles expose quality source count, reason, provenance, `token-quality-v1`, and spam evidence.
- Event pagination: renders 10 events initially, reveals 10 more with Show more, and reverses one page at a time with Show less while keeping the visible and total counts explicit.

Playwright is included as a dev dependency for local rendered-dashboard checks and screenshots.

## Token Labels

`analytics/seeds/token_metadata.csv` is a generated Ethereum-mainnet snapshot from the Trust Wallet, Uniswap, and CoinGecko token lists. `token_metadata_manifest.json` records upstream URLs, versions, commit SHA, synchronization time, and counts. `token_label_overrides.csv` is the reviewed manual layer and takes precedence for corrections or explicit spam classifications.

`token_rpc_metadata.csv` stores pinned-block `name`, `symbol`, and `decimals` responses for unverified contracts. Run `bun run labels:enrich --limit 100` to process the next unlabeled contracts by transfer count, `--retry-failed` to retry failures, or `--refresh` to reread already attempted contracts. RPC metadata never establishes trust, but its self-declared name and symbol are inputs to explainable spam heuristics.

`counterparty_code_metadata.csv` stores one evidence snapshot per Ethereum address: chain ID, pinned block/time, code state, exact EIP-7702 target when present, verified Safe singleton/version/owner-address count/threshold, canonical EntryPoint sender observations and provenance, fetch status, reason codes, and requested/effective coverage. `account_evidence_manifest.json` pins official Safe mainnet singleton deployments plus versioned EntryPoint releases, deployment blocks, and deployment transactions. Run `bun run addresses:enrich --limit 500` explicitly to process a ranked batch; EntryPoint scans are deployment-clamped, block-chunked, sender-batched, and independently retried. Empty code becomes `eoa_candidate`, ordinary code becomes `contract`, and unavailable code remains `unknown`. A failed code lookup becomes `partial`, not `failed`, when another source still supplied usable evidence. Safe and ERC-4337 evidence can refine the primary type without erasing either independent flag.

Registry membership supplies display metadata but is not a security guarantee. A reviewed manual approval or exact-address membership in at least two independent registries is `high_confidence`; exactly one registry is `listed`; RPC-only or absent registry evidence is `unknown`. CoinGecko-only OSCAR (`0xebb66a88cedd12bfe3a289df6dfee377f2963f12`) and PUPPIES (`0xcf91b70017eabde82c9671e30e5502d312ea6eb2`) therefore remain listed/unverified, not trusted. The separate classifier scores contract reputation and wallet-token interaction behavior; either can produce `suspected_spam`, while only a reviewed override produces final `spam`. No price, market-cap, volume, or liquidity API is used. Exact thresholds and limitations are documented in `docs/architecture.md` and `docs/data-model.md`.
