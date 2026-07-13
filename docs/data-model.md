# Data Model

The core grain is one row per wallet-relevant ERC20 transfer.

## Staging

### `stg_erc20_transfers`

Deduplicates raw transfer entities by `chain_id`, `transaction_hash`, and `log_index`. It normalizes all addresses to lowercase and standardizes block, transaction, token, `from`, `to`, and raw value fields.

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

Reads the fixture or live `counterparty_code_metadata` seed at one row per enriched address. Fields include `address_type` (`contract`, `wallet`, or `unknown`), `code_size_bytes`, pinned RPC block, fetch timestamp/status, and error code. Complete zero-byte results are wallets; complete positive-byte results are contracts; failures are unknown.

## Intermediate

### `int_wallet_transfer_events`

Filters staged transfers to configured wallets and adds:

- `direction`: `in` when the wallet is the recipient, `out` when it is the sender.
- `counterparty_address`: the other side of the transfer.
- `counterparty_type`: bytecode classification when enriched, otherwise `unknown`.
- `amount_decimal`: `value_raw / 10 ^ decimals` when metadata exists.

### `int_token_reputation`

One row per observed or labeled token contract. It produces `token_reputation`, a 0-100 `token_reputation_score`, semicolon-delimited `token_reputation_reasons`, and `token_reputation_version`. Address-based registry matches and manual overrides take precedence over deterministic metadata heuristics. Missing registry membership contributes no score.

### `int_wallet_token_interactions`

One row per wallet and token. It records transfer and distinct-counterparty counts, direction counts, first/last timestamps, active duration, a 0-100 `interaction_legitimacy_score`, reason codes, version, and `interaction_legitimacy` (`not_suspicious`, `uncertain`, or `suspicious`). It detects broad, bursty, one-direction transfer sprays without claiming transaction initiation.

### `int_classified_wallet_transfer_events`

Joins both evidence layers back to one-row-per-transfer events. Its effective `token_status` is one of `trusted`, `unverified`, `suspected_spam`, or `spam`. Manual spam has final precedence, followed by automated suspicion, then exact-address trust.

## Marts

### `wallet_events`

Dashboard-ready event table. This preserves the one-transfer grain and carries counterparty type, effective status, metadata provenance, both classification scores, reason codes, and classifier versions to every transfer.

### `graph_nodes`

Nodes for wallets, counterparties, and tokens. Wallet and counterparty nodes carry `address_type`; token nodes leave it null.

The dashboard export shortens counterparty labels for readability while keeping full addresses in the JSON node `address` field.

### `graph_edges`

Each wallet-counterparty-token-direction interaction produces two directed legs: `wallet_token` and `token_counterparty`. Inbound flow is counterparty to token to wallet; outbound flow is wallet to token to counterparty. This makes every exported token node part of the graph.

`amount_decimal_sum` remains null when token metadata is unavailable. It is never replaced with zero.

Graph edges carry effective status, metadata provenance, and both evidence layers so the static dashboard can remove suspected and reviewed spam before projecting direct wallet-counterparty links.

`counterparty_transfer_count` is the complete number of wallet-relevant ERC20 transfers for the wallet-counterparty pair across all tokens and both directions. It is repeated on each interaction edge so bounded graph exports retain the full-history activity metric used for gradual node sizing.

### `token_summary`

Transfer counts and token-flow totals by wallet, token, and direction.

`amount_decimal_sum` is null when token metadata is missing, so the dashboard can show that only raw units are available instead of implying a decimal-adjusted zero. `value_raw_sum` uses DuckDB `BIGNUM` and is serialized as a JSON string to preserve integer precision beyond JavaScript's safe-number range.

### `counterparty_summary`

Counts and first/last seen timestamps by wallet, counterparty, and direction.

### `timeline_daily`

Daily transfer counts and token-flow aggregates by wallet, token, and direction. Token addresses are part of the grain because decimal amounts from different assets cannot be meaningfully summed together. Raw totals are exact strings and decimal totals remain null without metadata.

### `pipeline_metadata`

One row per configured wallet containing chain, fixture-versus-HyperIndex source, generation time, complete transfer/token/counterparty/interaction/timeline counts, visible non-spam counts, hidden suspected/reviewed-spam counts, and first/last event timestamps.

The exporter enriches this row in `meta.json` with per-status event, interaction, and token-summary limits; global limits for other files; actual exported counts; `is_sampled`; and exact transfer/token/counterparty counts for all 15 non-empty combinations of the four statuses. These fields distinguish complete DuckDB mart counts from bounded static views and support exact dashboard status-filter statistics. The JSON subsets do not change any dbt mart grain.

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
- Classification scores constrained to 0-100 with non-empty reasons.
- Manual-spam, automated-suspicion, and trusted-status precedence.
- Valid pinned-block address types, fetch statuses, and bytecode-size consistency.
