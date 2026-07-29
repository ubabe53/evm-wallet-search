# Data Model

The core grain is one row per wallet-relevant `Transfer(address,address,uint256)` log, interpreted by ERC-20-oriented models. The signature alone does not prove ERC-20: ERC-721 uses the same signature, and the current wildcard indexer has no standards-disambiguation step. Until that gap is closed, a captured ERC-721-like token ID can occupy `value_raw` and must not be presented as a proven fungible quantity.

## Staging

### `stg_transfer_events`

Deduplicates wallet-relevant Transfer-signature entities by the canonical `(chain_id, transaction_hash, log_index)` key. The neutral name does not claim that the emitting contract implements ERC-20. It normalizes all addresses and the captured block hash to lowercase and standardizes block, transaction, emitting contract, emitted Transfer `from`/`to`, and raw third-value fields. The redundant HyperIndex entity ID is not retained in staging; downstream compatibility identifiers, where still required, are derived from the canonical key. Nullable `transaction_from_address` and `transaction_to_address` preserve selected top-level transaction envelope evidence. They remain null for legacy entities that predate this field selection; no directness is inferred from missing values.

`block_hash` is provided with each HyperIndex event and retained as event-level canonical-block evidence. In HyperIndex mode, `value_raw` is cast to text inside Postgres through `postgres_query` before DuckDB scans it. This lossless transport cast avoids converting unconstrained Postgres numeric values to floating point or scientific notation and preserves the exact integer emitted as the event's third value. Both live and fixture inputs already expose text, so staging does not apply a second redundant cast. The value remains unscaled raw evidence; its meaning is not guaranteed to be a fungible quantity until token standard is disambiguated.

### `stg_wallets`

Configured wallet targets at `(chain_id, wallet_address)` grain. `wallet_id` is not retained because chain plus normalized address is the canonical key. The current `ens` and `label` values remain pinned project configuration for presentation and snapshot labeling; they are not live ENS-resolution evidence and are not copied into event facts. The MVP contains one target:

- `vitalik.eth`
- `0xd8da6bf26964af9d7eed9e03e53415d37aa96045`

### `stg_account_evidence`

In live mode, reads `analytics/artifacts/account_evidence.duckdb` at one retained pinned-block observation per `(chain_id, address)`. Fixture mode returns an empty typed relation and does not ship an account-evidence CSV. The current scope fixes `chain_id = 1`. Each row preserves:

- `account_type`: `eoa_candidate`, `contract`, or retryable `unknown`.
- `code_state`: `no_code`, internal `eip7702_delegated`, `contract_code`, or `unknown`, plus exact byte length and delegation target when applicable.
- Concrete observation block number/hash/typed timestamp, `finality_policy`, singular `reason_code`, fetch status, schema version, and typed fetch timestamp.

Successful observations are immutable by default and therefore represent “observed at block,” not permanent identity. Failed calls are checkpointed but remain eligible on the next run. Safe and ERC-4337-specific evidence are not collected.

## Intermediate

### `int_token_enrichment`

Combines the generated Trust Wallet/Uniswap/CoinGecko/Coinbase Exchange registry, reviewed manual overrides, and pinned-block Ethereum RPC metadata into one resolved token-enrichment row at `(chain_id, token_address)` grain. This is an intermediate model rather than staging because it applies cross-source precedence and derives recognition and metadata availability. The current sources are Ethereum-only and therefore set `chain_id = 1`; the chain key remains explicit so a contract address is never treated as globally unique. Overrides take precedence for symbol, name, decimals, recognition, reason, and source URL. Coinbase-only rows intentionally leave decimals null because exchange trading precision is not ERC-20 decimal metadata.

The final metadata precedence is manual override, curated registry, then pinned-block Ethereum RPC metadata. RPC-derived fields may supply labels and decimals, but self-declared metadata cannot establish recognition.

The normalized fields are:

- `recognition_status`: `recognized` for at least one exact-address registry match or reviewed approval, otherwise `other`; a reviewed manual rejection takes precedence.
- `recognition_reason`, `recognition_source`, and `recognition_version`: the automatic decision evidence, with version `token-recognition-v1`.
- `metadata_source`: `trustwallet`, `uniswap`, `coingecko`, `coinbase`, their combined value, `manual`, or `ethereum_rpc`.
- `metadata_source_url`: upstream provenance for the label.
- `metadata_availability`: `complete`, `partial`, or `unavailable` based only on name, symbol, and decimals availability.
- `token_label_reason`: required human context for manual classifications.

Tokens without a registry match or manual recognition remain in event marts as `other`. Sourced token `decimals` remain nullable metadata; they never alter the exact emitted raw value.

Raw RPC observations remain separate in `token_rpc_metadata` (or `token_rpc_metadata_fixture` for deterministic fixture builds) at one row per attempted token address. That relation preserves the returned `name`, `symbol`, and `decimals` alongside `rpc_block_number`, `fetched_at`, `fetch_status`, and `error_code`. The resolved enrichment consumes complete or partial metadata and excludes failed-only attempts, but it does not copy RPC execution fields into every resolved token row.

### `int_wallet_transfer_events`

Filters staged transfers to configured wallets using `(chain_id, wallet_address)` and adds:

- `direction`: `self` when both emitted participants equal the wallet, otherwise `in` when the wallet is the recipient or `out` when it is the sender. The self branch is evaluated first.
- `counterparty_address`: the other side of an inbound/outbound transfer; for a self-transfer it equals the tracked wallet so the immutable event remains self-contained and auditable.
- `counterparty_account_type` plus the complete pinned observation, fetch status, reason codes, and evidence schema version; unenriched counterparties remain `unknown` / `not_fetched`.
- `value_raw`: the exact base-10 string emitted in the log. Token `decimals` remain adjacent sourced metadata so a future consumer can derive an amount with an explicit precision and presentation policy; the current model does not cast the raw value to floating point.
- automatic token recognition status, reason, source, and classifier version copied from token enrichment without changing the event grain.
- `transaction_sender_relation`: `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `from` and the emitted Transfer participants.
- `transaction_target_relation`: `token_contract`, `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `to`, the emitting token, and Transfer participants.
- `is_indirect`: true for an observed `transaction_from_address != from_address`, false for an observed match, and null when transaction-sender evidence is unavailable.

## Marts

### `wallet_events`

Application-serving event table. This preserves the immutable one-transfer grain, event-time block number/timestamp, and captured canonical block hash while carrying the canonical `(chain_id, wallet_address)` target key, emitted Transfer `from_address`/`to_address`, wallet-relative direction, nullable top-level transaction sender/target, sender/target relation codes, nullable indirect evidence, observed-at counterparty account evidence, recognition evidence, and metadata availability. Configured ENS and person-label text are not repeated on each event. Enrichment observation time never replaces event block evidence. The local API queries this mart with explicit filters, ordering, and pagination; the fixture demo exports a bounded subset.

### `graph_nodes`

Nodes for tracked addresses, external counterparties, and tokens participating in inbound/outbound interactions. Self-transfers do not create graph nodes or relationships. Counterparty nodes carry primary account type, code observation, fetch status, and reasons. Population coverage belongs to `pipeline_metadata`; tracked-address and token nodes leave account evidence null because this counterparty snapshot does not classify them.

The legacy fixture graph export shortens counterparty labels for readability while retaining full addresses in its payload. The current dashboard does not load or render these nodes.

### `graph_edges`

Each external wallet-counterparty-token-direction interaction produces two directed legs: `wallet_token` and `token_counterparty`. Inbound flow is counterparty to token to wallet; outbound flow is wallet to token to counterparty. Self-transfers remain in event and token-flow marts but are excluded from the external interaction graph. This makes every exported token node part of the graph.

Graph edges carry recognition and metadata provenance. They do not carry or derive token reputation evidence.

`counterparty_transfer_count` is the complete number of captured wallet-relevant Transfer-signature events for the wallet-counterparty pair across all emitting contracts and both directions. It is not a proven ERC-20-only count. It is repeated on each interaction edge for legacy bounded graph-export compatibility.

### `token_summary`

One row per wallet, emitting contract, recognition status, and exact counterparty account-evidence signature across inbound, outbound, and self activity. This serving grain supports inclusive account filtering. The local API filters cell rows and aggregates them back to one row per wallet and emitting contract before ranking and returning a bounded page; the fixture demo performs the equivalent operation over its small static payload. It records total, inbound, outbound, and self captured Transfer-signature event counts; the total reconciles as inbound + outbound + self. It also records confirmed-indirect inbound and outbound counts; distinct sender, recipient, and unioned external-counterparty address counts; token-decimals metadata; and the exact raw-third-value total. Without token-standard disambiguation, those counts and totals are ERC-20-intended rather than proven fungible-token measures.

`indirect_inbound_transfer_count` and `indirect_outbound_transfer_count` count only `is_indirect = true`. Legacy nulls are excluded rather than treated as direct or indirect, so each indirect count is bounded by its corresponding direction total.

`sender_account_count` counts distinct non-zero, non-self counterparties on inbound events. `recipient_account_count` applies the same exclusions on outbound events. `counterparty_count` is their distinct union, so it must not be calculated by adding the other two counts. These are event-address roles, not proof of human wallets or transaction initiation.

`value_raw_sum` uses DuckDB `BIGNUM` and is serialized as a JSON string to preserve integer precision beyond JavaScript's safe-number range. `token_decimals` remains sourced metadata at the same token-contract grain, but no floating-point normalized amount is materialized. The current dashboard table does not display token quantities.

### `counterparty_summary`

One row per wallet, chain, eligible counterparty, and recognition status. `transfer_count` is the sheer number of captured Transfer-signature events, not a proven ERC-20-only or distinct-transaction metric; inbound and outbound event counts reconcile to that total. The mart also records distinct-emitting-contract count, first/last event timestamps, primary account type, pinned code observation, provenance, and fetch status/reasons. Population coverage belongs to `pipeline_metadata`, not to an individual evidence row.

The ranking-serving mart excludes the zero address, the tracked wallet itself, and any counterparty address observed as an emitting token contract in the indexed wallet dataset. These exclusions do not delete rows from `wallet_events` or alter event totals.

### `timeline_daily`

Daily transfer counts and token-flow aggregates by wallet, token, recognition, exact counterparty account-evidence signature, and direction (`in`, `out`, or `self`). This mart remains the fixture-demo timeline source. The local API instead derives complete yearly overview or selected-year monthly event-count buckets directly from `wallet_events` so current manual recognition overrides and query predicates apply consistently. Self events remain in total counts but contribute to neither inbound nor outbound directional stacks. Token addresses remain part of the mart grain because raw values from different assets cannot be meaningfully summed together. Raw totals use arbitrary-precision integers in DuckDB and exact strings at JSON boundaries.

### `pipeline_metadata`

One row per `(chain_id, wallet_address)` containing the pinned configured ENS display text, fixture-versus-HyperIndex source, generation time, complete transfer/token/counterparty/interaction/timeline counts, recognized/other counts, first/last event timestamps, and account-evidence coverage metadata. Live rows also carry the completed snapshot run ID, cumulative start block, latest incremental start block, finalized end block and hash, `ethereum_finalized` policy, and scope version. These fields describe verified scan coverage; first/last event blocks do not. Fixture snapshot fields are null because deterministic fixture rows do not prove indexer coverage.

Account-evidence coverage uses `distinct_nonzero_nonself_event_counterparties` as its population scope. At the address grain, `eligible = classified + failed + not_checked`; the event-weighted fields apply the same statuses to captured Transfer-signature rows. Coverage rates are classified divided by eligible and are null only for an empty denominator. Observation block/time bounds and the schema version are derived only from successfully classified addresses. Fixture builds therefore report their eligible address/event populations as not checked while leaving successful-observation provenance null.

The fixture-demo exporter enriches this row in `meta.json` with returned counts, limits, and sampling state. The demo metadata must identify fixture provenance and must not imply that its counts describe complete HyperIndex history.

## Operational and application-owned local state

### `ops.pipeline_runs`

The live build wrapper creates this table inside `analytics/artifacts/live.duckdb`; dbt does not model, seed, replace, or export it. Its grain is one attempted run for `(chain_id, wallet_address, scope_version, from_block, to_block)`, identified by `run_id`. The row records the pinned configured label, inclusive interval, finalized end-block hash, number of matching events found in that interval, `running|completed|failed` status, completion time, and semantic scope version.

The first interval starts at HyperIndex `_meta.startBlock`. Only completed, exactly contiguous intervals advance the next start to the previous `to_block + 1`; failed rows remain auditable and retryable. The target is the newest block that is both fully processed by HyperIndex and no newer than Ethereum's current `finalized` head, capped by a configured HyperIndex end when present. Its canonical hash is fetched from Ethereum RPC. A run completes only after dbt succeeds. Rebuilding transformations while already current reuses the latest completed run rather than creating a false scan interval.

### `app.token_recognition_overrides`

The local API creates this table inside `analytics/artifacts/live.duckdb`; dbt does not model, seed, replace, or export it. Its grain and primary key are `(chain_id, token_address)`. `chain_id` is currently constrained to `1`, `status` is `recognized` or `other`, and `updated_at` records the latest mutation time. A row overrides automatic `wallet_events.recognition_status`; no row means automatic classification. Normal in-place dbt builds preserve the table, while deleting or replacing the DuckDB file loses this local-only state.

## Local API contract

The `/api/v1` service currently advertises response schema `dashboard-api-v13`. It serves only `analytics/artifacts/live.duckdb` in production mode and refuses fixture provenance, missing/unfinalized snapshot metadata, or a metadata run ID that does not match one completed `ops.pipeline_runs` row. It left-joins the application-owned override table before recognition, repeated inclusive `account`, optional literal `q`, and optional UTC date predicates are applied. `start` is inclusive and `end` is exclusive; they are `YYYY-MM-DD` dates and must be provided together with `start < end`. Omitting `account` selects all rows, including internal unresolved evidence; `account=eoa_candidate` or `account=contract` selects only that successfully classified type. `account=none` explicitly selects no rows and cannot be combined with another account value. For counterparty and graph rankings, recognition selects an inclusive address cohort: an address qualifies when at least one scoped event has the selected recognition status, then all of that address's events inside the remaining account/search/time scope contribute to its counts. This preserves mixed recognized/other relationships instead of splitting or dropping them. Event `value_raw` and token `value_raw_sum` fields cross the JSON boundary as exact strings. Version 10 added the yearly/monthly timeline drill-down contract while retaining version 9's `self` event direction and per-token `self_transfer_count`; version 11 added each timeline bucket's required `self_transfer_count`, keeping self events in the bucket total without folding them into inbound or outbound counts. Version 12 replaces `wallet_id` with `(chain_id, wallet_address)` throughout serving rows and keeps configured ENS text only in metadata. Version 13 removes token reputation status, quality evidence, and spam counters from event, summary, graph, metadata, and token responses; recognition evidence remains the only token-classification contract. Counterparty counts and graph compatibility relationships remain external-only. The service exposes:

- `metadata`: one provenance object for the configured wallet, including DuckDB generation time, contiguous finalized snapshot bounds, observed event block/time extrema, account-evidence coverage, `finality_status`, and API schema version. Event extrema remain separate from the indexer checkpoint;
- `summary`: one exact aggregate for the active selection, with transfer, distinct-token, distinct-counterparty, block, and event-time bounds;
- `events`: one row per immutable `wallet_events` row, ordered newest-first by block/transaction/log position and traversed with an opaque keyset cursor;
- `timeline`: one complete, gap-filled UTC series with exact total, inbound, outbound, and self captured-event counts; each bucket reconciles as `total = inbound + outbound + self`. `interval=year` returns the stable observed-year domain; `interval=month` requires one `year` and returns only that calendar window through the latest observed month when it is the boundary year. Recognition, account, and search filters can zero a bucket but do not remove its calendar position;
- `tokens`: one exact aggregate per emitting token contract, ranked after filtering and limited only after aggregation;
- `PUT /tokens/{token_address}/recognition`: persist `recognized` or `other`, returning the previous override so a client can undo exactly;
- `DELETE /tokens/{token_address}/recognition`: remove the override and return to the automatic result;
- `counterparties`: one exact aggregate per eligible address, with the same zero/self/emitting-token exclusions as the mart ranking, ranked by captured Transfer-signature event count after inclusive cohort selection;
- `graph`: the same one-row-per-eligible-counterparty grain and ordering as `counterparties`, including total, inbound, outbound, and distinct-emitting-contract counts for a direct aggregate edge.

Event responses distinguish `complete_matching_count` from `returned_count`, `limit`, `next_cursor`, and `is_paginated`. Ranked responses distinguish the complete matching item count from the returned top-N and `is_truncated`. Timeline `complete_matching_count` is the sum of exact captured-event counts while `returned_count` is the number of gap-filled buckets. `is_sampled` is always false because no matching source rows are randomly or permanently discarded. A top-N graph or ranking is a bounded presentation over a complete calculation, not a sample.

The React live adapter sends the same recognition, account, and search predicates to every endpoint, displays summary counts from the complete matching set, and distinguishes those totals from bounded token, counterparty, and event rows. `All years` requests yearly buckets without a date predicate. Selecting a year—through the dropdown or its bar—requests that year's monthly buckets while sending its exact half-open UTC range to summary, event, token, and counterparty requests. Selecting a month narrows those endpoints again; clearing the month returns to the selected year, while `All years` clears the time scope. The timeline request omits the active date predicate so all buckets in the current navigation scope remain available. Event expansion follows `next_cursor`; it never infers completeness from the current browser array. The static adapter remains separate, reads only generated fixture JSON, permits year/month timeline navigation, and does not claim that its bounded rows support dashboard period cross-filtering.

The fixture exporter records exact transfer/token/counterparty statistics for the nine combinations of three non-empty recognition selections and three non-empty EOA/Contract selections. The full account selection includes unresolved internal rows. Live serving computes only the requested selection.

## Tests

dbt tests enforce:

- Unique staged transfer IDs.
- No duplicate staged transfer logs.
- Non-null wallet, counterparty, and token addresses in dashboard marts.
- Valid graph edge endpoints.
- No orphan graph nodes.
- Valid graph edge roles and metadata source values.
- Valid `direction` and node type values.
- Valid metadata-availability values throughout enrichment and serving models.
- Valid automatic `recognized`/`other` values and `token-recognition-v1` provenance, plus persistent API override precedence and reset behavior.
- Null fixture snapshot claims and complete, internally ordered finalized snapshot fields for live builds.
- Manual recognition override precedence and `other` fallback behavior.
- Exact preservation of a maximum `uint256` raw event value through staging, event, token-summary, API, and fixture-export contracts.
- Valid, unique pinned-block RPC snapshots and RPC metadata precedence.
- Exact graph counterparty transfer counts across tokens and directions.
- Counterparty-summary totals that reconcile with inbound plus outbound counts, with ranking exclusions enforced.
- Exact transaction sender/target relation derivation, nullable legacy behavior, and indirect direction aggregates.
- Valid account-type/code-state precedence, exact 23-byte EIP-7702 evidence, and pinned observation/coverage consistency.
- Exact EIP-7702 code remains internal code state under an EOA-candidate primary type.
- Successful cached observations cannot be overwritten automatically, while failed code reads remain retryable.
- Fixture builds contain no account-evidence rows and keep their provenance bounds null.
- The fixture export's nine recognition/address-evidence token and counterparty candidate unions plus client aggregation from account cells back to displayed token and timeline grains.
