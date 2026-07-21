# Architecture

The primary product is a locally run, database-backed wallet analytics application. HyperIndex captures a narrow event set, dbt turns those events into DuckDB marts, a local API queries those marts on demand, and React renders the API responses. Static JSON is a separate fixture-only portfolio demo for GitHub Pages.

## Flow

1. `indexer/` runs Envio HyperIndex on Ethereum mainnet.
2. The HyperIndex handler stores one `Erc20Transfer` entity per wallet-relevant `Transfer(address,address,uint256)` log. This is intended for ERC-20 analytics, but ERC-721 uses the identical signature and the wildcard source currently has no standards-disambiguation step. It selects the top-level transaction `from` and `to` fields and stores them as nullable envelope evidence alongside the emitted Transfer `from`, `to`, and raw third value. HyperIndex raw-event storage is disabled because the normalized entity is the pipeline input and duplicate raw storage adds overhead.
3. In local-product mode, dbt-duckdb attaches HyperIndex Postgres read-only as the `hyperindex` catalog and reads `public."Erc20Transfer"`. Fixture mode is reserved for deterministic tests and the static GitHub Pages demo.
4. In live mode, dbt joins offline token inputs and the ignored `analytics/artifacts/account_evidence.duckdb` cache, separates metadata availability, token quality, and spam reputation, calculates interaction-legitimacy evidence, then builds marts into `analytics/artifacts/live.duckdb`. Fixture mode supplies an empty typed account-evidence relation rather than invented classifications.
5. The local FastAPI service opens `analytics/artifacts/live.duckdb` read-only and queries complete marts for filtered counts, ranked token/counterparty/graph results, and cursor-paginated events. It binds to loopback, requires HyperIndex provenance, and never uses the fixture database.
6. The Vite React dashboard calls the local API. Browser code never receives a Postgres DSN, DuckDB write access, or RPC credentials.
7. Separately, `scripts/export_dashboard.py` reads only `analytics/artifacts/fixture.duckdb` and creates bounded fixture JSON under `public/data/` for the GitHub Pages demo. Vite selects the live API adapter for `dashboard:dev` and the static adapter for `dashboard:build`; the two sources are never configured together.

## Local Application Contract

The local API is the serving boundary. Its public reputation control is a boolean `include_spam` predicate: false excludes both `suspected_spam` and reviewed `spam`, while true includes every internal status and quality. Within the repeated `account` query parameter, selected values use OR semantics; omission selects every value, while the exclusive `account=none` sentinel preserves an intentionally empty UI selection. The spam and account predicates compose with AND semantics. The optional literal substring query applies to event identity, transaction, date, direction, configured wallet, counterparty/account evidence, token, and metadata fields. The API applies these predicates before counts, ranking, graph limiting, or event pagination. It computes only the selection requested by the user; it does not precompute every possible selection.

API responses identify the configured wallet and chain, DuckDB transformation generation time, observed event block/time bounds, account-evidence observation coverage, API schema version, `completeness_scope: duckdb_snapshot`, and the currently unrecorded checkpoint/finality status. The event extrema are not an indexer checkpoint or proof of block-range continuity. Ranked responses distinguish the exact complete matching item count from the returned top-N limit and disclose `is_truncated`. Events use stable descending block/transaction/log keyset pagination, disclose the exact complete matching event count, and return an opaque next cursor. Every API response sets `is_sampled: false`; bounded ranking and pagination are presentation constraints, not source sampling.

React must not connect directly to HyperIndex Postgres. “Database-backed” means the local server owns DuckDB connections and exposes a typed, read-only application API. HyperIndex Postgres remains ingestion persistence rather than a browser-facing query service.

## Dashboard Behavior

In live mode, React sends spam, inclusive account-evidence, and literal text-search predicates to the API. They are applied first, before summary calculations, ranking, graph limiting, or event pagination. Safe and ERC-4337 remain independent account predicates, so an overlap row matches either selection but is counted once. The dashboard renders exact matching totals separately from the bounded rows returned to each panel and follows the event endpoint's opaque cursor on demand. The fixture demo applies equivalent controls only to its small generated payload. The dashboard hides suspected and reviewed spam by default and exposes one `Include spam` toggle. It does not expose token quality or the internal trusted/unverified distinction as filters or badges, and it does not trigger arbitrary wallet processing or new indexing work.

The graph payload preserves the analytical counterparty-token-wallet edge model, but the dashboard projects each interaction into one direct, directed wallet-counterparty link. Token symbols are rendered as edge labels instead of separate rhombus nodes. This keeps the visible topology focused on the configured address and addresses it interacted with. Captured Transfer-signature data alone cannot establish token standard or account type, so counterparties without successful pinned evidence remain `unknown`.

An explicit RPC enrichment step selects every distinct event counterparty exactly once after excluding the configured wallet and zero address. It resolves one concrete `safe` block (or a configured confirmed-head fallback), batches `eth_getCode`, and checkpoints results in a separate ignored DuckDB cache. Exact 23-byte code beginning `0xef0100` preserves its target as internal `eip7702_delegated` code state but remains an EOA candidate for public presentation; empty code is `eoa_candidate`; other code is `contract`; and failed reads are retryable `unknown`. Successful rows are never automatically refreshed. The stored block number, hash, timestamp, finality policy, fetch time, and reason make the historical observation explicit; no-code evidence does not prove an EOA, personhood, control, or permanence.

Safe and ERC-4337-specific collection are intentionally removed. A deployed Safe or smart account with bytecode is ordinary contract evidence. A counterfactual address with no code can appear as an EOA candidate under this deliberately bounded binary presentation; that limitation is disclosed rather than hidden behind speculative subtype detection.

Each rendered edge label combines the token symbol with that interaction's transfer count, for example `USDC x5`. This count remains at counterparty-token-direction grain; the counterparty circle uses the separate complete cross-token transfer count.

Visible blockchain identifiers are Etherscan navigation targets. Token-flow and event symbols link to `/token/{address}`, counterparty addresses link to `/address/{address}`, and event transaction controls link to `/tx/{hash}`. Cytoscape nodes open wallet or counterparty address pages, while projected interaction edges open the associated token contract. All navigation opens a new tab without granting the destination access to the dashboard window.

The local API returns a bounded ranked interaction page for the active filter selection, while the dashboard defaults to 25 and lets the user display 10, 25, 50, or 100 direct links. Endpoint filtering removes nodes that are not part of those displayed links. Links use a narrow activity-weighted range rather than scaling into heavy bands. Node hover focuses the immediate neighborhood, while edge hover focuses the selected interaction. Zoom bounds derive from the fitted graph size with absolute safety caps; pan movement is clamped around rendered bounds and a reset control restores the fitted view. Theater mode promotes the graph to a fixed viewport overlay, locks background scrolling, refits after the size change, and provides both a visible exit control and Escape-key exit.

Each exported interaction also carries the counterparty's complete wallet-level captured Transfer-signature event count across emitting contracts and directions. It is not a proven ERC-20-only count until token-standard disambiguation exists. The client uses a fixed base-10 logarithmic scale: 1 event is 26px, each tenfold increase adds 10.5px, and 10,000 or more caps at 68px. Sizing therefore remains based on full indexed history and stays stable across interaction limits, searches, and status filters.

The Ethereum zero address is excluded from the rendered interaction graph and the ranked counterparty summary because it represents token mint/burn mechanics rather than a navigable counterparty. The ranked summary also excludes the configured wallet itself and addresses observed as emitting token contracts. Their captured events remain in `wallet_events`, token summaries, totals, and event-query results so the underlying indexed evidence stays complete.

The panel currently labeled Top ERC-20 Counterparties ranks the sheer number of captured Transfer-signature events—not proven ERC-20 events or distinct transactions—and aggregates matching status-quality-account rows into one address. It shows observed-at account evidence, emitting-contract breadth, `Amount In / Out` event counts, and recency. The account-evidence multi-select scopes graph, ranking, events, timeline, token summaries, and statistics; Safe and ERC-4337 choices use inclusive independent predicates so overlap is retained without double counting. The token-flow panel sits below recent events and aggregates matching account-evidence cells back to one row per emitting contract before ranking and rendering. Its `Senders | Recipients` indicator counts distinct non-zero, non-self event counterparties rather than directional event frequency; raw third values are not presented. It also shows exact confirmed-indirect inbound and outbound counts. Recent events are paginated client-side in groups of 10.

Transaction initiation remains a separate event-time evidence layer from observed-at account and token classification. `direction` is still derived only from emitted Transfer `from`/`to` relative to the configured wallet. An event is `is_indirect = true` only when a selected top-level transaction sender exists and differs from Transfer `from`; it is false on an observed match and null for legacy rows without sender evidence. Sender and target relation codes describe exact address equality against Transfer participants and the emitting token contract. Recent events append `*` to `in` or `out` for confirmed mismatches, with a tooltip covering `transferFrom`, routers, Safe/account abstraction, and synthetic or spam emission. Neither spam status nor token quality changes these fields or establishes transaction-sender intent. The mismatch is not a spam signal by itself and does not establish execution path, intent, standards compliance, economic ownership, or historical account type.

Theme changes update the existing Cytoscape stylesheet in place. They do not recreate the graph or rerun its layout, so node positions, pan, and zoom remain stable. The graph container owns explicit light and dark palette variables to prevent effect-order races from applying the previous theme's label color.

Local API responses carry HyperIndex/DuckDB provenance, complete matching counts, minimum/maximum account-evidence observation block/time, scan coverage, returned row counts, and configured query limits. The dashboard renders a block range for mixed enrichment batches and a single block only when both bounds match. The fixture-demo `meta.json` carries the analogous source and sampling boundaries for the static demo. Neither path may present bounded results as complete indexed chain history.

## Token Label Flow

`scripts/sync_token_registry.py` explicitly fetches Ethereum token lists from Trust Wallet, Uniswap, and CoinGecko and writes a checked-in snapshot plus provenance manifest. Matching is by exact Ethereum contract address, never name or symbol. It is never invoked by dbt or the dashboard, so normal builds do not depend on network availability or mutable upstream data.

The pipeline keeps three independent dimensions. `metadata_availability` reports whether name, symbol, and decimals are `complete`, `partial`, or `unavailable`; it says nothing about trust. `token_quality` is `high_confidence` for a reviewed manual approval or exact-address membership in at least two independent registries, `listed` for exactly one registry, and `unknown` for RPC-only or absent registry evidence. `token_quality_sources`, its count, reason, evidence provenance, and `token-quality-v1` make that decision reproducible. The checked-in registry's legacy status field does not establish effective trust.

CoinGecko absence is neutral, and CoinGecko-only exact-address membership is `listed`, not trusted. In particular, OSCAR (`0xebb66a88cedd12bfe3a289df6dfee377f2963f12`) and PUPPIES (`0xcf91b70017eabde82c9671e30e5502d312ea6eb2`) are `listed` quality and `unverified` status internally. The local API calculates complete counts for the active spam and inclusive account selection so summary cards do not mistake paginated rows for full matching history.

RPC enrichment is a separate explicit batch operation. It ranks unverified contracts by wallet transfer count, pins one Ethereum block, and reads optional ERC20 `name`, `symbol`, and `decimals` methods. Results are stored in an offline seed with `complete`, `partial`, or `failed` status. Merge precedence is manual override, curated registry, then RPC metadata. RPC rows never establish trust, although their names and symbols can trigger explainable reputation signals.

## Balanced Spam Policy

Token reputation, token quality, and interaction legitimacy are modeled independently, then combined into the dashboard status. Precedence is reviewed manual `spam`, automated reputation or suspicious interaction behavior as `suspected_spam`, `high_confidence` quality as `trusted`, and otherwise `unverified`. A reviewed approval can therefore still be superseded by later spam evidence, while a one-registry listing is never promoted to trusted.

That four-value status remains an internal, evidence-bearing model. The user-facing projection has only `Spam` versus no spam flag: `suspected_spam` and `spam` both render as `Spam`, while `trusted` and `unverified` render without a reputation label. This intentionally does not claim that an unflagged token is trusted. Scores, reason codes, provenance, and classifier versions remain in DuckDB and the typed transitional payload, but the dashboard does not expose them as filters, badges, or search terms.

Contract-level reputation signals in `token-reputation-v2` are URL-bearing metadata (70), claim language (30), configured-wallet impersonation (60), native BTC/ETH impersonation (65), Trust Wallet/Uniswap identity collision (65), and CoinGecko-only identity collision (35). Scores are capped at 100 and require 60 for `suspected_spam`. Version 2 adds the quality-aware precedence in this feature; the weaker CoinGecko collision therefore cannot classify a token by itself.

Wallet-token behavior in `interaction-legitimacy-v2` detects at least 100 counterparties with no more than 1.25 transfers per counterparty (45). It adds evidence for a distribution completed within 72 hours (20) and at least 98% one-direction activity (15). The outbound-initiator component (20) is added only when at least 98% of activity is outbound and every outbound row has selected transaction-sender evidence matching the configured wallet as Transfer sender. Scores of 60 or more are `suspicious`, 20-59 are `uncertain`, and lower scores are `not_suspicious`.

Every score has stable reason codes and a classifier version. `not_suspicious` means no current heuristic fired; it does not prove benign intent. The evidence-backed outbound reason is `mass_outbound_transaction_sender_matches_wallet`; it is never emitted for missing or mismatched transaction senders. Indirect counts and relation codes remain descriptive evidence and do not add a spam score on their own.

Runtime settings resolve from shell environment first, git-ignored `config.yaml` second, and the configured public RPC fallback last. The fallback is allowed only for read-only Ethereum metadata. Envio and live Postgres credentials remain required for their respective operations.

## Fixture Demo Export Policy

GitHub Pages is a portfolio demonstration, not the complete application runtime. Its generated JSON must come from deterministic fixture data, remain small enough for static hosting, and display its fixture provenance and sampling boundaries prominently. It may demonstrate filters and interactions without claiming complete live-wallet rankings or history.

The exporter still contains legacy candidate-union logic that evaluates the equivalent of 6,615 status-quality-account selections. That design belongs only to deterministic fixture-demo compatibility and must not be expanded. Complete local counts and rankings now use on-demand DuckDB API queries.

Docker is the intended distribution mechanism for the local product, not for GitHub Pages. Before adding it, define separate services for indexing, transformation, API, and frontend as needed; persist Postgres and DuckDB deliberately; keep secrets outside images; add health and readiness behavior; and ensure fixture-demo commands cannot overwrite live local artifacts.

## Scope Boundaries

- Included: wallet-relevant `Transfer(address,address,uint256)` logs on Ethereum mainnet, interpreted by ERC-20-oriented models with the explicit limitation that the source does not prove token standard.
- Included: nullable top-level transaction sender and target fields selected on those events.
- Included: raw token units and decimal-adjusted token amounts when token metadata exists.
- Excluded: traces, internal calls, state deltas, native ETH transfers, approvals, swaps, NFT-specific disambiguation/interpretation, USD pricing, and arbitrary wallet lookup.

## Documentation Rule

When implementation changes, update the related documentation in the same change:

- Indexer behavior changes: update `README.md` and this file.
- Model shape or grain changes: update `docs/data-model.md`.
- Command or setup changes: update `README.md` and `docs/operations.md`.
- Local API contract changes: update `docs/data-model.md`, the server contract, and frontend client types.
- Fixture-demo JSON contract changes: update `docs/data-model.md`, `src/data.ts`, and exporter tests.
