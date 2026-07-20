# Architecture

The MVP is intentionally batch-oriented. HyperIndex captures a narrow event set, dbt turns those events into wallet analytics marts, and the dashboard serves static JSON generated from DuckDB.

## Flow

1. `indexer/` runs Envio HyperIndex on Ethereum mainnet.
2. The HyperIndex handler stores one `Erc20Transfer` entity per ERC20 transfer involving the configured wallet. It selects the top-level transaction `from` and `to` fields and stores them as nullable envelope evidence alongside the emitted Transfer `from`, `to`, and raw value. HyperIndex raw-event storage is disabled because the normalized entity is the pipeline input and duplicate raw storage adds overhead.
3. `analytics/` reads a checked-in, deterministically sampled Parquet snapshot of the latest 90 indexed days for `vitalik.eth` by default, capped at 100 transfers per UTC day. CI selects the separate six-row semantic fixture for exact edge-case tests. In live mode, dbt-duckdb attaches HyperIndex Postgres read-only as the `hyperindex` catalog and reads `public."Erc20Transfer"`.
4. dbt joins offline token and observed-at counterparty account-evidence snapshots, separates metadata availability, token quality, and spam reputation, calculates interaction-legitimacy evidence, then builds marts into `analytics/wallet_analytics.duckdb`.
5. `scripts/export_dashboard.py` exports deterministic, bounded mart views to `public/data/*.json`. The complete marts remain in DuckDB.
6. The Vite React dashboard reads the JSON files directly.

## Dashboard Behavior

The dashboard is static and client-side only. Status AND quality AND inclusive account-evidence eligibility are applied first, before text search, summary calculations, graph limiting, counterparty aggregation, timeline filtering, token aggregation, or event pagination. Safe and ERC-4337 remain independent account predicates, so an overlap row matches either selection but is counted once. Its filter bar derives matching interaction IDs from eligible event rows so transaction-hash searches keep the corresponding token summaries and graph path visible. The quality filter defaults to `high_confidence`; `listed` and `unknown` remain explicit, discoverable options. It does not trigger arbitrary wallet processing or new indexing work.

The graph JSON preserves the analytical counterparty-token-wallet edge model, but the dashboard projects each interaction into one direct, directed wallet-counterparty link. Token symbols are rendered as edge labels instead of separate rhombus nodes. This keeps the visible topology focused on the configured address and addresses it interacted with. ERC20 event data alone cannot establish account type, so counterparties without successful pinned evidence remain `unknown`.

An explicit RPC enrichment step records selected counterparties at one pinned Ethereum block. Exact 23-byte code beginning `0xef0100` is `eip7702_delegated` and preserves its 20-byte delegation target; no-code results are `eoa_candidate`; other code is contract evidence; and failed code reads are `unknown`. No-code evidence does not prove an EOA, personhood, control, or permanence.

Safe verification is deliberately narrower than interface detection. For ordinary code, storage slot zero must point to an official Ethereum-mainnet Safe singleton in the checked-in manifest; for delegated code, the exact delegation target supplies the singleton candidate. `getOwners()` and `getThreshold()` must both decode consistently, owners must be distinct non-zero addresses, and the threshold must be between one and the owner-address count. Interface-only responses or unlisted singleton targets remain contract evidence. The dashboard displays the threshold as address-level evidence, not as a claim about people.

ERC-4337 detection is positive event evidence: an address must appear as indexed `sender` in `UserOperationEvent` logs emitted by a versioned canonical EntryPoint from the checked-in manifest. Every EntryPoint range is clamped to `max(requested_start, deployment_block)`, then split into bounded block chunks and bounded OR-lists of sender topics. Failed chunks are retried independently; successful chunks remain usable, while exhausted chunks make the row `partial` and are recorded separately from merged effective coverage. A failed code lookup also becomes `partial` whenever the EntryPoint scan or another source supplied usable evidence; `failed` is reserved for rows with no usable source result. The manifest pins each mainnet deployment block, transaction, release, and explorer provenance. Each snapshot records the matched EntryPoint, observation blocks, count, work-unit sizes, successful ranges, failed ranges, status, and reason codes. Safe and ERC-4337 flags are independent because one address can satisfy both. Primary `account_type` precedence is delegated EOA, verified Safe, observed ERC-4337 account, other contract, EOA candidate, then unknown.

Each rendered edge label combines the token symbol with that interaction's transfer count, for example `USDC x5`. This count remains at counterparty-token-direction grain; the counterparty circle uses the separate complete cross-token transfer count.

Visible blockchain identifiers are Etherscan navigation targets. Token-flow and event symbols link to `/token/{address}`, counterparty addresses link to `/address/{address}`, and event transaction controls link to `/tx/{hash}`. Cytoscape nodes open wallet or counterparty address pages, while projected interaction edges open the associated token contract. All navigation opens a new tab without granting the destination access to the dashboard window.

The static export contains at most 250 ranked interactions per status-quality-account-evidence cell, while the dashboard defaults to 25 and lets the user display 10, 25, 50, or 100 direct links. Endpoint filtering removes nodes that are not part of those displayed links. Links use a narrow activity-weighted range rather than scaling into heavy bands. Node hover focuses the immediate neighborhood, while edge hover focuses the selected interaction. Zoom bounds derive from the fitted graph size with absolute safety caps; pan movement is clamped around rendered bounds and a reset control restores the fitted view. Theater mode promotes the graph to a fixed viewport overlay, locks background scrolling, refits after the size change, and provides both a visible exit control and Escape-key exit.

Each exported interaction also carries the counterparty's complete wallet-level ERC20 transfer count across tokens and directions. The client uses a fixed base-10 logarithmic scale: 1 transfer is 26px, each tenfold increase adds 10.5px, and 10,000 or more caps at 68px. Sizing therefore remains based on full indexed history and stays stable across interaction limits, searches, and status filters.

The Ethereum zero address is excluded from the rendered interaction graph and the ranked counterparty summary because it represents token mint/burn mechanics rather than a navigable counterparty. The ranked summary also excludes the configured wallet itself and addresses observed as ERC20 token contracts. Their transfers remain in `wallet_events`, token summaries, totals, and recent-event JSON so the underlying analytics stay complete.

The Top ERC-20 Counterparties panel ranks the sheer number of transfer events—not distinct transactions—and aggregates matching status-quality-account rows into one address. It shows observed-at account evidence, token breadth, `Amount In / Out` event counts, and recency. The account-evidence multi-select scopes graph, ranking, events, timeline, token summaries, and statistics; Safe and ERC-4337 choices use inclusive independent predicates so overlap is retained without double counting. The token-flow panel sits below recent events and aggregates matching account-evidence cells back to one row per token before ranking and rendering. Its `Senders | Recipients` indicator counts distinct non-zero, non-self event counterparties rather than directional event frequency; raw token amounts are not presented. It also shows exact confirmed-indirect inbound and outbound counts. Recent events are paginated client-side in groups of 10.

Transaction initiation remains a separate event-time evidence layer from observed-at account and token classification. `direction` is still derived only from emitted Transfer `from`/`to` relative to the configured wallet. An event is `is_indirect = true` only when a selected top-level transaction sender exists and differs from Transfer `from`; it is false on an observed match and null for legacy rows without sender evidence. Sender and target relation codes describe exact address equality against Transfer participants and the emitting token contract. Recent events append `*` to `in` or `out` for confirmed mismatches, with a tooltip covering `transferFrom`, routers, Safe/account abstraction, and synthetic or spam emission. Neither spam status nor token quality changes these fields or establishes transaction-sender intent. The mismatch is not a spam signal by itself and does not establish execution path, intent, standards compliance, economic ownership, or historical account type.

Theme changes update the existing Cytoscape stylesheet in place. They do not recreate the graph or rerun its layout, so node positions, pan, and zoom remain stable. The graph container owns explicit light and dark palette variables to prevent effect-order races from applying the previous theme's label color.

`meta.json` carries fixture-versus-HyperIndex provenance, fixture kind, fixed-window size, indexed event block bounds, complete mart counts, minimum/maximum account-evidence observation block/time, scan coverage, exported row counts, and configured export limits into the static application. The dashboard identifies the 90-day snapshot and renders its exact event block range; it renders an evidence block range for mixed enrichment batches and a single block only when both evidence bounds match. This keeps a bounded snapshot, bounded evidence scans, and bounded live exports distinct from complete chain history.

## Token Label Flow

`scripts/sync_token_registry.py` explicitly fetches Ethereum token lists from Trust Wallet, Uniswap, and CoinGecko and writes a checked-in snapshot plus provenance manifest. Matching is by exact Ethereum contract address, never name or symbol. It is never invoked by dbt or the dashboard, so normal builds do not depend on network availability or mutable upstream data.

The pipeline keeps three independent dimensions. `metadata_availability` reports whether name, symbol, and decimals are `complete`, `partial`, or `unavailable`; it says nothing about trust. `token_quality` is `high_confidence` for a reviewed manual approval or exact-address membership in at least two independent registries, `listed` for exactly one registry, and `unknown` for RPC-only or absent registry evidence. `token_quality_sources`, its count, reason, evidence provenance, and `token-quality-v1` make that decision reproducible. The checked-in registry's legacy status field does not establish effective trust.

CoinGecko absence is neutral, and CoinGecko-only exact-address membership is `listed`, not trusted. In particular, OSCAR (`0xebb66a88cedd12bfe3a289df6dfee377f2963f12`) and PUPPIES (`0xcf91b70017eabde82c9671e30e5502d312ea6eb2`) are `listed` quality and `unverified` status. The exporter calculates complete counts for every non-empty status, quality, and inclusive account selection so summary cards do not mistake bounded JSON rows for full history.

RPC enrichment is a separate explicit batch operation. It ranks unverified contracts by wallet transfer count, pins one Ethereum block, and reads optional ERC20 `name`, `symbol`, and `decimals` methods. Results are stored in an offline seed with `complete`, `partial`, or `failed` status. Merge precedence is manual override, curated registry, then RPC metadata. RPC rows never establish trust, although their names and symbols can trigger explainable reputation signals.

## Balanced Spam Policy

Token reputation, token quality, and interaction legitimacy are modeled independently, then combined into the dashboard status. Precedence is reviewed manual `spam`, automated reputation or suspicious interaction behavior as `suspected_spam`, `high_confidence` quality as `trusted`, and otherwise `unverified`. A reviewed approval can therefore still be superseded by later spam evidence, while a one-registry listing is never promoted to trusted.

Contract-level reputation signals in `token-reputation-v2` are URL-bearing metadata (70), claim language (30), configured-wallet impersonation (60), native BTC/ETH impersonation (65), Trust Wallet/Uniswap identity collision (65), and CoinGecko-only identity collision (35). Scores are capped at 100 and require 60 for `suspected_spam`. Version 2 adds the quality-aware precedence in this feature; the weaker CoinGecko collision therefore cannot classify a token by itself.

Wallet-token behavior in `interaction-legitimacy-v2` detects at least 100 counterparties with no more than 1.25 transfers per counterparty (45). It adds evidence for a distribution completed within 72 hours (20) and at least 98% one-direction activity (15). The outbound-initiator component (20) is added only when at least 98% of activity is outbound and every outbound row has selected transaction-sender evidence matching the configured wallet as Transfer sender. Scores of 60 or more are `suspicious`, 20-59 are `uncertain`, and lower scores are `not_suspicious`.

Every score has stable reason codes and a classifier version. `not_suspicious` means no current heuristic fired; it does not prove benign intent. The evidence-backed outbound reason is `mass_outbound_transaction_sender_matches_wallet`; it is never emitted for missing or mismatched transaction senders. Indirect counts and relation codes remain descriptive evidence and do not add a spam score on their own.

Runtime settings resolve from shell environment first, git-ignored `config.yaml` second, and the configured public RPC fallback last. The fallback is allowed only for read-only Ethereum metadata. Envio and live Postgres credentials remain required for their respective operations.

## Static Export Policy

The live wallet history is much larger than a useful in-browser graph. The exporter therefore writes:

- The 1,000 newest transfer events per status-quality-account-evidence cell.
- Both edge legs for the top 250 interactions per status-quality-account-evidence cell, ranked by transfer count then recency.
- Only the endpoint nodes used by those graph edges.
- Every per-account-cell row for the exact top-500 token candidate union and exact top-50 counterparty candidate union across all 6,615 non-empty status-quality-account selections.
- The 5,000 newest daily timeline rows per status-quality-account-evidence cell, written back in chronological order.

Candidate selection encodes each row and each selection as bitsets, evaluates all 15 × 7 × 63 selections in one DuckDB query per ranking, ranks combined transfer counts before limiting, and exports every cell row for each candidate. This is proof-equivalent to issuing 6,615 separate ranking queries while avoiding round-trip overhead. Safe and ERC-4337 membership bits are independent and inclusive. The browser applies the same predicate and aggregates token/timeline cells back to token and daily-token-direction grains before rendering. `meta.json` records `15`, `7`, `63`, `6,615`, candidate counts, exact-ranking guarantees, complete/exported counts, and `is_sampled`. Exact candidate-union rankings remain valid when `is_sampled` is true; other bounded views still represent samples. These bounds affect only `public/data/*.json`. DuckDB retains the complete indexed dataset. This feature adds no price, market-cap, volume, or liquidity API.

## Scope Boundaries

- Included: ERC20 `Transfer` events on Ethereum mainnet.
- Included: nullable top-level transaction sender and target fields selected on those events.
- Included: raw token units and decimal-adjusted token amounts when token metadata exists.
- Excluded: traces, internal calls, state deltas, native ETH transfers, approvals, swaps, NFT transfers, USD pricing, and arbitrary wallet lookup.

## Documentation Rule

When implementation changes, update the related documentation in the same change:

- Indexer behavior changes: update `README.md` and this file.
- Model shape or grain changes: update `docs/data-model.md`.
- Command or setup changes: update `README.md` and `docs/operations.md`.
- Dashboard JSON contract changes: update `docs/data-model.md` and frontend types in `src/data.ts`.
