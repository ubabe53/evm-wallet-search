# Data Model

The core grain is one row per wallet-relevant `Transfer(address,address,uint256)` log, interpreted by ERC-20-oriented models. The signature alone does not prove ERC-20: ERC-721 uses the same signature, and the current wildcard indexer has no standards-disambiguation step. Until that gap is closed, a captured ERC-721-like token ID can occupy `value_raw` and must not be presented as a proven fungible quantity.

## Staging

### `stg_erc20_transfers`

Deduplicates raw Transfer-signature entities by `chain_id`, `transaction_hash`, and `log_index`. It normalizes all addresses to lowercase and standardizes block, transaction, emitting contract, emitted Transfer `from`/`to`, and raw third-value fields. Nullable `transaction_from_address` and `transaction_to_address` preserve selected top-level transaction envelope evidence. They remain null for legacy entities that predate this field selection; no directness is inferred from missing values.

In HyperIndex mode, `value_raw` is cast to text inside Postgres through `postgres_query` before DuckDB scans it. This avoids converting unconstrained Postgres numeric values to floating point or scientific notation and preserves the exact integer emitted as the event's third value. Its meaning is not guaranteed to be a fungible quantity until token standard is disambiguated.

### `stg_wallets`

Configured wallets. The MVP contains one pinned wallet:

- `vitalik.eth`
- `0xd8da6bf26964af9d7eed9e03e53415d37aa96045`

### `stg_token_metadata`

Combines the generated Trust Wallet/Uniswap/CoinGecko/Coinbase Exchange registry with reviewed manual overrides. Overrides take precedence for symbol, name, decimals, base status, reason, and source URL, while exact-address registry membership remains separately available to recognition and quality classification. Coinbase-only rows intentionally leave decimals null because exchange trading precision is not ERC-20 decimal metadata.

The final metadata precedence is manual override, curated registry, then pinned-block Ethereum RPC metadata. RPC-derived fields may supply labels and decimals, but their status remains `unverified` because contracts self-declare these values.

The normalized fields are:

- `token_status`: reviewed manual base status; the generated registry's legacy status does not establish effective trust.
- `recognition_status`: `recognized` for at least one exact-address registry match or reviewed approval, otherwise `other`; a reviewed manual rejection takes precedence.
- `recognition_reason`, `recognition_source`, and `recognition_version`: the automatic decision evidence, with version `token-recognition-v1`.
- `metadata_source`: `trustwallet`, `uniswap`, `coingecko`, `coinbase`, their combined value, `manual`, or `ethereum_rpc`.
- `metadata_source_url`: upstream provenance for the label.
- `metadata_availability`: `complete`, `partial`, or `unavailable` based only on name, symbol, and decimals availability.
- `token_quality`: `high_confidence`, `listed`, or `unknown`.
- `token_quality_sources` and `token_quality_source_count`: exact-address registry evidence only; manual approval is recorded in the reason/provenance rather than inflated into a registry count.
- `token_quality_reason`, `token_quality_provenance`, and `token_quality_version`: reproducible evidence with version `token-quality-v1`.
- `token_label_reason`: required human context for manual classifications.
- `rpc_block_number`, `rpc_fetch_status`, and `rpc_error_code`: audit fields for RPC enrichment attempts.

Unknown tokens remain in event marts as internally `unverified` and publicly `other`, with `amount_decimal = null` when decimals are unavailable.

### `stg_counterparty_metadata`

In live mode, reads `analytics/artifacts/account_evidence.duckdb` at one row per `(chain_id, address)` historical observation. Fixture mode returns an empty typed relation and does not ship an account-evidence CSV. The current scope fixes `chain_id = 1`. Each row preserves:

- `account_type`: `eoa_candidate`, `contract`, or retryable `unknown`.
- `code_state`: `no_code`, internal `eip7702_delegated`, `contract_code`, or `unknown`, plus exact byte length and delegation target when applicable.
- Concrete observation block number/hash/timestamp, the `safe` or confirmed-head fallback policy, fetch status/reason, schema version, and fetch time.

Successful observations are immutable by default and therefore represent “observed at block,” not permanent identity. Failed calls are checkpointed but remain eligible on the next run. Safe and ERC-4337-specific evidence are not collected.

## Intermediate

### `int_wallet_transfer_events`

Filters staged transfers to configured wallets and adds:

- `direction`: `in` when the wallet is the recipient, `out` when it is the sender.
- `counterparty_address`: the other side of the transfer.
- `counterparty_account_type` plus the complete pinned observation, Safe evidence, ERC-4337 evidence, fetch status, reason codes, and coverage fields; unenriched counterparties remain `unknown` / `not_fetched`.
- `amount_decimal`: `value_raw / 10 ^ decimals` when metadata exists.
- automatic token recognition status, reason, source, and classifier version copied from token enrichment without changing the event grain.
- `transaction_sender_relation`: `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `from` and the emitted Transfer participants.
- `transaction_target_relation`: `token_contract`, `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `to`, the emitting token, and Transfer participants.
- `is_indirect`: true for an observed `transaction_from_address != from_address`, false for an observed match, and null when transaction-sender evidence is unavailable.

### `int_token_reputation`

One row per observed or labeled token contract. It produces `token_reputation`, a 0-100 `token_reputation_score`, semicolon-delimited `token_reputation_reasons`, and `token_reputation_version`, while carrying the separate quality evidence. `token-reputation-v2` records the quality-aware precedence introduced here. Reviewed spam takes precedence over deterministic metadata heuristics; automated suspicion precedes high-confidence trust. Missing registry membership contributes no score.

### `int_wallet_token_interactions`

One row per wallet and token. It records transfer and distinct-counterparty counts, direction counts, confirmed-indirect inbound/outbound counts, transaction-sender evidence coverage, first/last timestamps, active duration, a 0-100 `interaction_legitimacy_score`, reason codes, version, and `interaction_legitimacy` (`not_suspicious`, `uncertain`, or `suspicious`). It detects broad, bursty, one-direction transfer sprays. In `interaction-legitimacy-v2`, the outbound-initiator score and `mass_outbound_transaction_sender_matches_wallet` reason require complete outbound transaction-sender evidence matching the wallet; unknown or mismatched senders do not receive that component. A mismatch alone is not a spam classification signal.

### `int_classified_wallet_transfer_events`

Joins both evidence layers back to one-row-per-transfer events. Its effective `token_status` is one of `trusted`, `unverified`, `suspected_spam`, or `spam`. Reviewed manual spam has final precedence, followed by automated suspicion, then `high_confidence` quality; every other case is unverified.

These four values are an internal classification contract, not four user choices. The presentation layer maps `suspected_spam` and `spam` to one `Spam` state and maps `trusted` and `unverified` to no reputation badge. The `Include spam` predicate controls whether the first pair is excluded or included. Token quality, scores, reason codes, provenance, and versions remain stored for audit and future product decisions.

## Marts

### `wallet_events`

Application-serving event table. This preserves the immutable one-transfer grain and event-time block fields while carrying emitted Transfer `from_address`/`to_address`, wallet-relative direction, nullable top-level transaction sender/target, sender/target relation codes, nullable indirect evidence, observed-at counterparty account evidence, automatic recognition evidence, metadata availability, token quality evidence, effective internal status, both classification scores, reason codes, and classifier versions. Enrichment observation time never replaces event block number or timestamp. The local API queries this mart with explicit filters, ordering, and pagination; the fixture demo exports a bounded subset.

### `graph_nodes`

Nodes for tracked addresses, counterparties, and tokens. Counterparty nodes carry primary account type, code observation, fetch status, reasons, and coverage bounds. Tracked-address and token nodes leave account evidence null because this counterparty snapshot does not classify them.

The presentation layer shortens counterparty labels for readability while retaining full addresses in the API or demo payload. It exposes only EOA and Contract labels; internal EIP-7702 evidence appears only in the EOA tooltip, and unresolved rows receive no type badge.

### `graph_edges`

Each wallet-counterparty-token-direction interaction produces two directed legs: `wallet_token` and `token_counterparty`. Inbound flow is counterparty to token to wallet; outbound flow is wallet to token to counterparty. This makes every exported token node part of the graph.

`amount_decimal_sum` remains null when token metadata is unavailable. It is never replaced with zero.

Graph edges carry effective status, metadata provenance, and both evidence layers so the application query can exclude suspected and reviewed spam before projecting direct wallet-counterparty links.

`counterparty_transfer_count` is the complete number of captured wallet-relevant Transfer-signature events for the wallet-counterparty pair across all emitting contracts and both directions. It is not a proven ERC-20-only count. It is repeated on each interaction edge so bounded graph exports retain the full-history activity metric used for gradual node sizing.

### `token_summary`

One row per wallet, emitting contract, effective status, quality, and exact counterparty account-evidence signature across inbound and outbound activity. This serving grain supports inclusive account filtering. The local API filters cell rows and aggregates them back to one row per wallet and emitting contract before ranking and returning a bounded page; the fixture demo performs the equivalent operation over its small static payload. It records total, inbound, and outbound captured Transfer-signature event counts; confirmed-indirect inbound and outbound counts; distinct sender, recipient, and unioned-counterparty address counts; token reputation evidence; decimal-adjusted total when metadata exists; and exact raw-third-value total. Without token-standard disambiguation, those counts and totals are ERC-20-intended rather than proven fungible-token measures.

`indirect_inbound_transfer_count` and `indirect_outbound_transfer_count` count only `is_indirect = true`. Legacy nulls are excluded rather than treated as direct or indirect, so each indirect count is bounded by its corresponding direction total.

`sender_account_count` counts distinct non-zero, non-self counterparties on inbound events. `recipient_account_count` applies the same exclusions on outbound events. `counterparty_count` is their distinct union, so it must not be calculated by adding the other two counts. These are event-address roles, not proof of human wallets or transaction initiation.

`amount_decimal_sum` is null when token metadata is missing rather than implying a decimal-adjusted zero. `value_raw_sum` uses DuckDB `BIGNUM` and is serialized as a JSON string to preserve integer precision beyond JavaScript's safe-number range. Both fields remain in the data contract, but the current dashboard table does not display amounts.

### `counterparty_summary`

One row per wallet, chain, eligible counterparty, effective token status, and token quality. `transfer_count` is the sheer number of captured Transfer-signature events, not a proven ERC-20-only or distinct-transaction metric; inbound and outbound event counts reconcile to that total. The mart also records distinct-emitting-contract count, first/last event timestamps, primary account type, pinned code observation, provenance, fetch status/reasons, and coverage bounds.

The ranking-serving mart excludes the zero address, the tracked wallet itself, and any counterparty address observed as an emitting token contract in the indexed wallet dataset. These exclusions do not delete rows from `wallet_events` or alter event totals.

### `timeline_daily`

Daily transfer counts and token-flow aggregates by wallet, token, status, quality, exact counterparty account-evidence signature, and direction. This mart remains available for the fixture demo and a future time-series endpoint; the current local dashboard API does not expose a timeline route. Token addresses remain part of the displayed grain because decimal amounts from different assets cannot be meaningfully summed together. Raw totals are exact strings and decimal totals remain null without metadata.

### `pipeline_metadata`

One row per configured wallet containing chain, fixture-versus-HyperIndex source, generation time, complete transfer/token/counterparty/interaction/timeline counts, visible non-spam counts, hidden suspected/reviewed-spam counts, first/last event timestamps, and account-evidence coverage metadata. Evidence metadata includes enriched/complete address counts, minimum and maximum observation blocks/timestamps across enrichment batches, scan scope/range, and schema version. Fixture bounds are null because fixture mode contains no account evidence. Equal live bounds represent one snapshot; unequal bounds are an observation range and must not be collapsed to the newest batch.

The fixture-demo exporter enriches this row in `meta.json` with returned counts, limits, and sampling state. The demo metadata must identify fixture provenance and must not imply that its counts describe complete HyperIndex history.

## Local API contract

The `/api/v1` service currently advertises response schema `dashboard-api-v2`. It reads only `analytics/artifacts/live.duckdb` in read-only mode and refuses any database whose `pipeline_metadata.data_source` is not `hyperindex`. Common `include_spam`, repeated inclusive `account`, and optional literal `q` predicates are applied to `wallet_events` before exact calculations. Omitting `account` selects all rows, including internal unresolved evidence; `account=eoa_candidate` or `account=contract` selects only that successfully classified type. `account=none` explicitly selects no rows and cannot be combined with another account value. The service exposes:

- `metadata`: one provenance object for the configured wallet, including DuckDB generation time, observed event block/time extrema, account-evidence coverage, `finality_status`, and API schema version. Event extrema are not an indexer checkpoint or a block-continuity claim;
- `summary`: one exact aggregate for the active selection, with transfer, distinct-token, distinct-counterparty, block, and event-time bounds;
- `events`: one row per immutable `wallet_events` row, ordered newest-first by block/transaction/log position and traversed with an opaque keyset cursor;
- `tokens`: one exact aggregate per emitting token contract, ranked after filtering and limited only after aggregation;
- `counterparties`: one exact aggregate per eligible address, with the same zero/self/emitting-token exclusions as the mart ranking, ranked after filtering;
- `graph`: one exact wallet-counterparty-token-direction interaction per row, ranked after filtering while retaining the counterparty's complete cross-token activity count for stable node sizing.

Event responses distinguish `complete_matching_count` from `returned_count`, `limit`, `next_cursor`, and `is_paginated`. Ranked responses distinguish the complete matching item count from the returned top-N and `is_truncated`. `is_sampled` is always false because no matching source rows are randomly or permanently discarded. A top-N graph or ranking is a bounded presentation over a complete calculation, not a sample.

The React live adapter sends the same predicate set to every endpoint, displays summary counts from the complete matching set, and distinguishes those totals from bounded graph, token, counterparty, and event rows. Event expansion follows `next_cursor`; it never infers completeness from the current browser array. The static adapter remains separate and reads only generated fixture JSON.

The current transitional exporter also records exact transfer/token/counterparty statistics for all 315 combinations of 15 non-empty status selections, 7 non-empty quality selections, and 3 non-empty EOA/Contract selections. The full account selection includes unresolved internal rows. This candidate-union contract is legacy behavior and is not the target serving model.

## Tests

dbt tests enforce:

- Unique staged transfer IDs.
- No duplicate staged transfer logs.
- Non-null wallet, counterparty, and token addresses in dashboard marts.
- Valid graph edge endpoints.
- No orphan graph nodes.
- Valid graph edge roles and metadata source values.
- Valid `direction` and node type values.
- Valid non-null token statuses throughout event, graph, token-summary, and timeline models.
- Valid metadata-availability and token-quality values, source-count reconciliation, non-empty provenance, `token-quality-v1`, and quality-aware `token-reputation-v2`.
- Explicit CoinGecko-only OSCAR and PUPPIES coverage proving `listed`/`unverified`, not trusted.
- Manual override precedence and unverified fallback behavior.
- Valid, unique pinned-block RPC snapshots and RPC metadata precedence.
- Exact graph counterparty transfer counts across tokens and directions.
- Counterparty-summary totals that reconcile with inbound plus outbound counts, with ranking exclusions enforced.
- Classification scores constrained to 0-100 with non-empty reasons.
- Exact transaction sender/target relation derivation, nullable legacy behavior, indirect direction aggregates, and evidence-backed interaction-legitimacy reasons.
- Synthetic broad-outbound classifier cases proving the initiator component is added for complete sender matches and withheld for unknown or mismatched senders.
- Manual-spam, automated-suspicion, and trusted-status precedence.
- Valid account-type/code-state precedence, exact 23-byte EIP-7702 evidence, and pinned observation/coverage consistency.
- Exact EIP-7702 code remains internal code state under an EOA-candidate primary type.
- Successful cached observations cannot be overwritten automatically, while failed code reads remain retryable.
- Fixture builds contain no account-evidence rows and keep their provenance bounds null.
- Reviewed-spam, automated-suspicion, high-confidence-trust, and unverified fallback precedence.
- The fixture export's legacy 315-selection token/counterparty candidate unions plus client aggregation from account cells back to displayed token and timeline grains. This is deterministic demo compatibility coverage, not the live serving contract, and should be simplified rather than expanded.
