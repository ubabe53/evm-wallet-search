# Architecture

The MVP is intentionally batch-oriented. HyperIndex captures a narrow event set, dbt turns those events into wallet analytics marts, and the dashboard serves static JSON generated from DuckDB.

## Flow

1. `indexer/` runs Envio HyperIndex on Ethereum mainnet.
2. The HyperIndex handler stores one `Erc20Transfer` entity per ERC20 transfer involving the configured wallet. It selects the top-level transaction `from` and `to` fields and stores them as nullable envelope evidence alongside the emitted Transfer `from`, `to`, and raw value. HyperIndex raw-event storage is disabled because the normalized entity is the pipeline input and duplicate raw storage adds overhead.
3. `analytics/` reads local fixture seeds by default. In live mode, dbt-duckdb attaches HyperIndex Postgres read-only as the `hyperindex` catalog and reads `public."Erc20Transfer"`.
4. dbt joins offline token and pinned-block counterparty account-evidence snapshots, calculates explainable token-reputation and interaction-legitimacy evidence, then builds marts into `analytics/wallet_analytics.duckdb`.
5. `scripts/export_dashboard.py` exports deterministic, bounded mart views to `public/data/*.json`. The complete marts remain in DuckDB.
6. The Vite React dashboard reads the JSON files directly.

## Dashboard Behavior

The dashboard is static and client-side only. Its filter bar derives matching interaction IDs from event rows so transaction-hash searches keep the corresponding token summaries and graph path visible. It does not trigger arbitrary wallet processing or new indexing work.

The graph JSON preserves the analytical counterparty-token-wallet edge model, but the dashboard projects each interaction into one direct, directed wallet-counterparty link. Token symbols are rendered as edge labels instead of separate rhombus nodes. This keeps the visible topology focused on the configured address and addresses it interacted with. ERC20 event data alone cannot establish account type, so counterparties without successful pinned evidence remain `unknown`.

An explicit RPC enrichment step records selected counterparties at one pinned Ethereum block. Exact 23-byte code beginning `0xef0100` is `eip7702_delegated` and preserves its 20-byte delegation target; no-code results are `eoa_candidate`; other code is contract evidence; and failed code reads are `unknown`. No-code evidence does not prove an EOA, personhood, control, or permanence.

Safe verification is deliberately narrower than interface detection. For ordinary code, storage slot zero must point to an official Ethereum-mainnet Safe singleton in the checked-in manifest; for delegated code, the exact delegation target supplies the singleton candidate. `getOwners()` and `getThreshold()` must both decode consistently, owners must be distinct non-zero addresses, and the threshold must be between one and the owner-address count. Interface-only responses or unlisted singleton targets remain contract evidence. The dashboard displays the threshold as address-level evidence, not as a claim about people.

ERC-4337 detection is positive event evidence: an address must appear as indexed `sender` in `UserOperationEvent` logs emitted by a versioned canonical EntryPoint from the checked-in manifest. Every EntryPoint range is clamped to `max(requested_start, deployment_block)`, then split into bounded block chunks and bounded OR-lists of sender topics. Failed chunks are retried independently; successful chunks remain usable, while exhausted chunks make the row `partial` and are recorded separately from merged effective coverage. The manifest pins each mainnet deployment block, transaction, release, and explorer provenance. Each snapshot records the matched EntryPoint, observation blocks, count, work-unit sizes, successful ranges, failed ranges, status, and reason codes. Safe and ERC-4337 flags are independent because one address can satisfy both. Primary `account_type` precedence is delegated EOA, verified Safe, observed ERC-4337 account, other contract, EOA candidate, then unknown.

Each rendered edge label combines the token symbol with that interaction's transfer count, for example `USDC x5`. This count remains at counterparty-token-direction grain; the counterparty circle uses the separate complete cross-token transfer count.

Visible blockchain identifiers are Etherscan navigation targets. Token-flow and event symbols link to `/token/{address}`, counterparty addresses link to `/address/{address}`, and event transaction controls link to `/tx/{hash}`. Cytoscape nodes open wallet or counterparty address pages, while projected interaction edges open the associated token contract. All navigation opens a new tab without granting the destination access to the dashboard window.

The static export contains at most 250 ranked interactions, while the dashboard defaults to 25 and lets the user display 10, 25, 50, or 100 direct links. Endpoint filtering removes nodes that are not part of those displayed links. Links use a narrow activity-weighted range rather than scaling into heavy bands. Node hover focuses the immediate neighborhood, while edge hover focuses the selected interaction. Zoom bounds derive from the fitted graph size with absolute safety caps; pan movement is clamped around rendered bounds and a reset control restores the fitted view. Theater mode promotes the graph to a fixed viewport overlay, locks background scrolling, refits after the size change, and provides both a visible exit control and Escape-key exit.

Each exported interaction also carries the counterparty's complete wallet-level ERC20 transfer count across tokens and directions. The client uses a fixed base-10 logarithmic scale: 1 transfer is 26px, each tenfold increase adds 10.5px, and 10,000 or more caps at 68px. Sizing therefore remains based on full indexed history and stays stable across interaction limits, searches, and status filters.

The Ethereum zero address is excluded from the rendered interaction graph and the ranked counterparty summary because it represents token mint/burn mechanics rather than a navigable counterparty. The ranked summary also excludes the configured wallet itself and addresses observed as ERC20 token contracts. Their transfers remain in `wallet_events`, token summaries, totals, and recent-event JSON so the underlying analytics stay complete.

The Top ERC-20 Counterparties panel ranks the sheer number of transfer events—not distinct transactions—and aggregates selected token-status rows into one address. It shows pinned account evidence, token breadth, `Amount In / Out` event counts, and recency. The account-evidence multi-select scopes the graph, ranking, and recent events; its Safe and ERC-4337 choices use inclusive independent predicates so overlap is retained. The token-flow panel sits below recent events and combines both directions into one row per token. Its `Senders | Recipients` indicator counts distinct non-zero, non-self event counterparties rather than directional event frequency; raw token amounts are not presented. It also shows exact confirmed-indirect inbound and outbound counts. Recent events are paginated client-side in groups of 10.

Transaction initiation remains a separate event-time evidence layer from observed-at account classification. `direction` is still derived only from emitted Transfer `from`/`to` relative to the configured wallet. An event is `is_indirect = true` only when a selected top-level transaction sender exists and differs from Transfer `from`; it is false on an observed match and null for legacy rows without sender evidence. Sender and target relation codes describe exact address equality against Transfer participants and the emitting token contract. Recent events append `*` to `in` or `out` for confirmed mismatches, with a tooltip covering `transferFrom`, routers, Safe/account abstraction, and synthetic or spam emission. The mismatch is not a spam signal by itself and does not establish execution path, intent, standards compliance, economic ownership, or historical account type.

Theme changes update the existing Cytoscape stylesheet in place. They do not recreate the graph or rerun its layout, so node positions, pan, and zoom remain stable. The graph container owns explicit light and dark palette variables to prevent effect-order races from applying the previous theme's label color.

`meta.json` carries fixture-versus-HyperIndex provenance, complete mart counts, account-evidence observation block/time and coverage, exported row counts, and configured export limits into the static application. The dashboard must display this metadata so fixture data, bounded evidence scans, and bounded live exports cannot be confused with complete indexed chain history.

## Token Label Flow

`scripts/sync_token_registry.py` explicitly fetches Ethereum token lists from Trust Wallet, Uniswap, and CoinGecko and writes a checked-in snapshot plus provenance manifest. Matching is by exact Ethereum contract address, never name or symbol. It is never invoked by dbt or the dashboard, so normal builds do not depend on network availability or mutable upstream data.

Manual overrides have precedence over the generated registry. Exact registry matches are `trusted`; reviewed overrides may set any supported status; every unmatched contract starts `unverified`. CoinGecko absence is not a negative signal. Spam eligibility and selected statuses are applied in the client before query filtering, graph limiting, and event pagination. The exporter calculates complete counts for every non-empty status combination so summary cards do not mistake bounded JSON rows for full history.

RPC enrichment is a separate explicit batch operation. It ranks unverified contracts by wallet transfer count, pins one Ethereum block, and reads optional ERC20 `name`, `symbol`, and `decimals` methods. Results are stored in an offline seed with `complete`, `partial`, or `failed` status. Merge precedence is manual override, curated registry, then RPC metadata. RPC rows never establish trust, although their names and symbols can trigger explainable reputation signals.

## Balanced Spam Policy

Token reputation and interaction legitimacy are modeled independently, then combined into the dashboard status. Manual `spam` wins; automated reputation or suspicious interaction behavior becomes `suspected_spam`; otherwise a registry match stays `trusted` and an unmatched contract stays `unverified`.

Contract-level reputation signals in `token-reputation-v1` are URL-bearing metadata (70), claim language (30), configured-wallet impersonation (60), native BTC/ETH impersonation (65), Trust Wallet/Uniswap identity collision (65), and CoinGecko-only identity collision (35). Scores are capped at 100 and require 60 for `suspected_spam`. The weaker CoinGecko collision therefore cannot classify a token by itself.

Wallet-token behavior in `interaction-legitimacy-v2` detects at least 100 counterparties with no more than 1.25 transfers per counterparty (45). It adds evidence for a distribution completed within 72 hours (20) and at least 98% one-direction activity (15). The outbound-initiator component (20) is added only when at least 98% of activity is outbound and every outbound row has selected transaction-sender evidence matching the configured wallet as Transfer sender. Scores of 60 or more are `suspicious`, 20-59 are `uncertain`, and lower scores are `not_suspicious`.

Every score has stable reason codes and a classifier version. `not_suspicious` means no current heuristic fired; it does not prove benign intent. The evidence-backed outbound reason is `mass_outbound_transaction_sender_matches_wallet`; it is never emitted for missing or mismatched transaction senders. Indirect counts and relation codes remain descriptive evidence and do not add a spam score on their own.

Runtime settings resolve from shell environment first, git-ignored `config.yaml` second, and the configured public RPC fallback last. The fallback is allowed only for read-only Ethereum metadata. Envio and live Postgres credentials remain required for their respective operations.

## Static Export Policy

The live wallet history is much larger than a useful in-browser graph. The exporter therefore writes:

- The 1,000 newest transfer events per token status.
- Both edge legs for the top 250 interactions per token status, ranked by transfer count then recency.
- Only the endpoint nodes used by those graph edges.
- The top 500 token summary rows per status, plus the union of address candidates needed to calculate the exact top 50 counterparties for every non-empty status combination.
- The 5,000 newest daily timeline rows, written back in chronological order.

Combined status-balanced rows are sorted globally after selection, preserving activity and recency ordering. Counterparty candidates are ranked by their combined transfer-event count before limiting, then every status row for each selected address is exported so browser-side filtering can reconstruct the same ranking. These bounds affect only `public/data/*.json`. dbt models in `analytics/wallet_analytics.duckdb` retain the complete indexed dataset and remain the source for full-history analysis.

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
