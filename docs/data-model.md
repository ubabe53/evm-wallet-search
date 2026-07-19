# Data Model

The core grain is one row per wallet-relevant ERC20 transfer.

## Staging

### `stg_erc20_transfers`

Deduplicates raw transfer entities by `chain_id`, `transaction_hash`, and `log_index`. It normalizes all addresses to lowercase and standardizes block, transaction, token, emitted Transfer `from`/`to`, and raw value fields. Nullable `transaction_from_address` and `transaction_to_address` preserve selected top-level transaction envelope evidence. They remain null for legacy entities that predate this field selection; no directness is inferred from missing values.

In HyperIndex mode, `value_raw` is cast to text inside Postgres through `postgres_query` before DuckDB scans it. This avoids converting unconstrained Postgres numeric values to floating point or scientific notation and preserves exact ERC20 integer units.

### `stg_wallets`

Configured wallets. The MVP contains one pinned wallet:

- `vitalik.eth`
- `0xd8da6bf26964af9d7eed9e03e53415d37aa96045`

### `stg_token_metadata`

Combines the generated Trust Wallet/Uniswap/CoinGecko registry with reviewed manual overrides. Overrides take precedence for symbol, name, decimals, status, reason, and source URL.

The final metadata precedence is manual override, curated registry, then pinned-block Ethereum RPC metadata. RPC-derived fields may supply labels and decimals, but their status remains `unverified` because contracts self-declare these values.

The normalized fields are:

- `token_status`: base metadata status before behavioral classification.
- `metadata_source`: `trustwallet`, `uniswap`, `coingecko`, their combined value, `manual`, or `ethereum_rpc`.
- `metadata_source_url`: upstream provenance for the label.
- `token_label_reason`: required human context for manual classifications.
- `rpc_block_number`, `rpc_fetch_status`, and `rpc_error_code`: audit fields for RPC enrichment attempts.

Unknown tokens remain in event marts as `unverified`, with `amount_decimal = null` when decimals are unavailable. Missing registry membership never implies spam.

### `stg_counterparty_metadata`

Reads the fixture or live `counterparty_code_metadata` seed at one row per `(chain_id, address)` evidence snapshot. The current scope fixes `chain_id = 1`. The row preserves:

- `account_type`: `eoa_candidate`, `eip7702_delegated`, `safe`, `erc4337_account`, `contract`, or `unknown`.
- `code_state`, exact byte length, observation block/time, and the EIP-7702 target only when code is exactly `0xef0100` plus 20 bytes.
- Independent `safe_verified` and `erc4337_observed` fields so overlapping evidence is not lost.
- Safe singleton/version, verification status, owner-address count, and threshold. The addresses themselves are not exported and counts do not imply people.
- ERC-4337 matched event count, first/last observation blocks, and pipe-delimited canonical EntryPoint address/version/source/deployment-block provenance when multiple versions match.
- Deployment-clamped effective coverage, exhausted chunk ranges, and the block-chunk and sender-batch sizes used for bounded `eth_getLogs` work. Effective coverage merges adjacent successful chunks; it never spans a failed chunk.
- `fetch_status`, stable `reason_codes`, evidence schema version, fetch time, coverage scope, and coverage start/end blocks.

Primary account-type precedence is delegated EOA, verified Safe, canonical EntryPoint sender, other contract code, no-code EOA candidate, then unknown. A failed code read is unknown. `partial` means some evidence source was unavailable or inconsistent even when code still supports a bounded primary type; for ERC-4337 it preserves successful effective coverage and names every exhausted block chunk.

## Intermediate

### `int_wallet_transfer_events`

Filters staged transfers to configured wallets and adds:

- `direction`: `in` when the wallet is the recipient, `out` when it is the sender.
- `counterparty_address`: the other side of the transfer.
- `counterparty_account_type` plus the complete pinned observation, Safe evidence, ERC-4337 evidence, fetch status, reason codes, and coverage fields; unenriched counterparties remain `unknown` / `not_fetched`.
- `amount_decimal`: `value_raw / 10 ^ decimals` when metadata exists.
- `transaction_sender_relation`: `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `from` and the emitted Transfer participants.
- `transaction_target_relation`: `token_contract`, `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `to`, the emitting token, and Transfer participants.
- `is_indirect`: true for an observed `transaction_from_address != from_address`, false for an observed match, and null when transaction-sender evidence is unavailable.

### `int_token_reputation`

One row per observed or labeled token contract. It produces `token_reputation`, a 0-100 `token_reputation_score`, semicolon-delimited `token_reputation_reasons`, and `token_reputation_version`. Address-based registry matches and manual overrides take precedence over deterministic metadata heuristics. Missing registry membership contributes no score.

### `int_wallet_token_interactions`

One row per wallet and token. It records transfer and distinct-counterparty counts, direction counts, confirmed-indirect inbound/outbound counts, transaction-sender evidence coverage, first/last timestamps, active duration, a 0-100 `interaction_legitimacy_score`, reason codes, version, and `interaction_legitimacy` (`not_suspicious`, `uncertain`, or `suspicious`). It detects broad, bursty, one-direction transfer sprays. In `interaction-legitimacy-v2`, the outbound-initiator score and `mass_outbound_transaction_sender_matches_wallet` reason require complete outbound transaction-sender evidence matching the wallet; unknown or mismatched senders do not receive that component. A mismatch alone is not a spam classification signal.

### `int_classified_wallet_transfer_events`

Joins both evidence layers back to one-row-per-transfer events. Its effective `token_status` is one of `trusted`, `unverified`, `suspected_spam`, or `spam`. Manual spam has final precedence, followed by automated suspicion, then exact-address trust.

## Marts

### `wallet_events`

Dashboard-ready event table. This preserves the one-transfer grain and carries emitted Transfer `from_address`/`to_address`, wallet-relative direction, nullable top-level transaction sender/target, sender/target relation codes, nullable indirect evidence, observed-at counterparty account evidence, effective token status, metadata provenance, both classification scores, reason codes, and classifier versions to every transfer.

### `graph_nodes`

Nodes for tracked addresses, counterparties, and tokens. Counterparty nodes carry primary account type, code observation, independent Safe/ERC-4337 flags and display evidence, fetch status, reasons, and coverage bounds. Tracked-address and token nodes leave account evidence null because this counterparty snapshot does not classify them.

The dashboard export shortens counterparty labels for readability while keeping full addresses in the JSON node `address` field.

### `graph_edges`

Each wallet-counterparty-token-direction interaction produces two directed legs: `wallet_token` and `token_counterparty`. Inbound flow is counterparty to token to wallet; outbound flow is wallet to token to counterparty. This makes every exported token node part of the graph.

`amount_decimal_sum` remains null when token metadata is unavailable. It is never replaced with zero.

Graph edges carry effective status, metadata provenance, and both evidence layers so the static dashboard can remove suspected and reviewed spam before projecting direct wallet-counterparty links.

`counterparty_transfer_count` is the complete number of wallet-relevant ERC20 transfers for the wallet-counterparty pair across all tokens and both directions. It is repeated on each interaction edge so bounded graph exports retain the full-history activity metric used for gradual node sizing.

### `token_summary`

One row per wallet and token across inbound and outbound activity. It records total, inbound, and outbound ERC20 transfer-event counts; confirmed-indirect inbound and outbound counts; distinct sender, recipient, and unioned-counterparty address counts; token reputation evidence; decimal-adjusted total when available; and exact raw total.

`indirect_inbound_transfer_count` and `indirect_outbound_transfer_count` count only `is_indirect = true`. Legacy nulls are excluded rather than treated as direct or indirect, so each indirect count is bounded by its corresponding direction total.

`sender_account_count` counts distinct non-zero, non-self counterparties on inbound events. `recipient_account_count` applies the same exclusions on outbound events. `counterparty_count` is their distinct union, so it must not be calculated by adding the other two counts. These are event-address roles, not proof of human wallets or transaction initiation.

`amount_decimal_sum` is null when token metadata is missing rather than implying a decimal-adjusted zero. `value_raw_sum` uses DuckDB `BIGNUM` and is serialized as a JSON string to preserve integer precision beyond JavaScript's safe-number range. Both fields remain in the data contract, but the current dashboard table does not display amounts.

### `counterparty_summary`

One row per wallet, chain, eligible counterparty, and effective token status. `transfer_count` is the sheer number of ERC20 `Transfer` events, not a distinct-transaction metric; inbound and outbound event counts reconcile to that total. The mart also records distinct-token count, first/last timestamps, primary account type, pinned code observation, independent Safe/ERC-4337 evidence, provenance, fetch status/reasons, and coverage bounds.

The ranking-serving mart excludes the zero address, the tracked wallet itself, and any counterparty address observed as an ERC20 token contract in the indexed wallet dataset. These exclusions do not delete rows from `wallet_events` or alter token totals.

### `timeline_daily`

Daily transfer counts and token-flow aggregates by wallet, token, and direction. Token addresses are part of the grain because decimal amounts from different assets cannot be meaningfully summed together. Raw totals are exact strings and decimal totals remain null without metadata.

### `pipeline_metadata`

One row per configured wallet containing chain, fixture-versus-HyperIndex source, generation time, complete transfer/token/counterparty/interaction/timeline counts, visible non-spam counts, hidden suspected/reviewed-spam counts, first/last event timestamps, and account-evidence coverage metadata. Evidence metadata includes enriched/complete address counts, Safe and ERC-4337 positive-evidence counts, observation block/time, scan scope/range, and schema version.

The exporter enriches this row in `meta.json` with complete token-summary and counterparty-summary row counts; per-status event, interaction, and token-summary limits; the per-status-combination counterparty ranking limit; the global timeline limit; actual exported counts; `is_sampled`; and exact transfer/token/counterparty counts for all 15 non-empty combinations of the four statuses. Counterparty candidate selection ranks combined address activity before limiting and exports every status row for each candidate, preserving exact top-50 browser rankings for every status combination. `is_sampled` covers every bounded export, including both summary files. These fields distinguish complete DuckDB mart counts from bounded static views and support exact dashboard status-filter statistics. The JSON subsets do not change any dbt mart grain.

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
- Manual override precedence and unverified fallback behavior.
- Valid, unique pinned-block RPC snapshots and RPC metadata precedence.
- Exact graph counterparty transfer counts across tokens and directions.
- Counterparty-summary totals that reconcile with inbound plus outbound counts, with ranking exclusions enforced.
- Classification scores constrained to 0-100 with non-empty reasons.
- Exact transaction sender/target relation derivation, nullable legacy behavior, indirect direction aggregates, and evidence-backed interaction-legitimacy reasons.
- Synthetic broad-outbound classifier cases proving the initiator component is added for complete sender matches and withheld for unknown or mismatched senders.
- Manual-spam, automated-suspicion, and trusted-status precedence.
- Valid account-type/code-state precedence, exact 23-byte EIP-7702 evidence, and pinned observation/coverage consistency.
- Safe types backed by official-singleton and internally consistent owner-address/threshold evidence; interface-only fixtures cannot become Safe.
- ERC-4337 types backed by positive canonical EntryPoint sender evidence, with Safe/ERC-4337 overlap retained.
