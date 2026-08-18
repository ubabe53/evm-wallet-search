# Data Model

## Scan-job contract

`ScanJob` is an orchestration object, not an event fact. Its key is `job_id`; it carries the requested wallet input, canonical `(chain_id=1, wallet_address)`, label, `status` (`queued|running|completed|failed`), integer progress, the wallet's first missing `from_block`, finalized `to_block`, timestamps, failure message, and (when resolved) ENS resolver source plus finalized observation block/hash/timestamp. ENS labels are mutable enrichment: the server-side adapter accepts conservative ASCII ENS names and resolves them through the pinned Ethereum mainnet registry/resolver at one finalized block. The explicit worker persists that provenance in the staged DuckDB run records before validated atomic publication.

The wallet list is a bounded list of completed `(chain_id, wallet_address, label, status)` entries derived from the complete multi-wallet artifact and successful in-process jobs.

The core grain is one row per wallet-relevant `Transfer(address,address,uint256)` log, interpreted by ERC-20-oriented models. The signature alone does not prove ERC-20: ERC-721 uses the same signature, and the current wildcard indexer has no standards-disambiguation step. Until that gap is closed, a captured ERC-721-like token ID can occupy `value_raw` and must not be presented as a proven fungible quantity.

## Staging

### `stg_transfer_events`

Deduplicates wallet-relevant Transfer-signature entities by the canonical `(chain_id, transaction_hash, log_index)` key. The neutral name does not claim that the emitting contract implements ERC-20. It normalizes all addresses and the captured block hash to lowercase and standardizes block, transaction, emitting contract, emitted Transfer `from`/`to`, and raw third-value fields. The redundant HyperIndex entity ID is not retained in staging; downstream compatibility identifiers, where still required, are derived from the canonical key. Nullable `transaction_from_address` and `transaction_to_address` preserve selected top-level transaction envelope evidence. They remain null for legacy entities that predate this field selection; no directness is inferred from missing values.

`block_hash` is provided with each HyperIndex event and retained as event-level canonical-block evidence. In HyperIndex mode, `value_raw` is cast to text inside Postgres through `postgres_query` before DuckDB scans it. This lossless transport cast avoids converting unconstrained Postgres numeric values to floating point or scientific notation and preserves the exact integer emitted as the event's third value. Both live and fixture inputs already expose text, so staging does not apply a second redundant cast. The value remains unscaled raw evidence; its meaning is not guaranteed to be a fungible quantity until token standard is disambiguated.

The checked-in public demo contains 90 unsampled Transfer-signature events captured by HyperIndex for the Gitcoin Schelling Point multisig (`0x11c24f0031b4c35e2e9353764edc61299291e0af`). Its recorded scan covers blocks 0–25,739,543 through finalized hash `0x5374be585630353358d7c6a0b20106fc74c45577264cbe6a70ad8e4b0ed5f484`; event-bearing blocks span 15,616,484–20,442,331. `analytics/seeds/demo_snapshot_manifest.json` carries the exact extraction, enrichment, sampling, and official wallet-attribution provenance. These historical rows are real emitted-log evidence, but they are not a current wallet view and the shared signature does not prove ERC-20.

The original 100-row synthetic dataset remains separate at `raw_transfer_events_fixture.csv` and is selected only by `fixture_dataset: synthetic`. It exercises semantic edge cases without making blockchain claims. `scripts/generate_fixture_events.py` and `tests/test_fixture_seed.py` guard its reproducibility; `scripts/generate_mainnet_demo.py` and `tests/test_mainnet_demo.py` guard the reviewed historical snapshot.

Live staging reads whichever durable raw relations exist in the same persistent Postgres database: Envio's normal `public."Erc20Transfer"` entity table, the worker-owned `wallet_scan.transfer_events` table populated by isolated bounded jobs, or both. At least one must exist. Both have the same event grain and exact fields. When both are available, staging compares every evidence field for repeated canonical keys and fails the build on any mismatch; equivalent duplicates use an explicit normal-source-first order. This is shared raw persistence, not a per-wallet table: one event involving two scanned wallets is still stored once.

### `wallet_scan.ingestion_runs` (Postgres)

One completed raw-ingestion checkpoint per `(chain_id, wallet_address, from_block, to_block, scope_version)`. It records the finalized `to_block_hash`, exact number of rows observed in the isolated bounded schema (including zero), status, and completion time. Immediately before the merge, the helper requires Envio's isolated `envio_chains` row to match the requested start/end, reach the end, and carry a completed `ready_at`; it also requires an authoritative finalized-block resolver to return that exact endpoint hash. The Envio checkpoint condition is rechecked inside the transactional merge before insertion, while the external RPC hash check necessarily occurs just before that database transaction. A checkpoint therefore proves that the raw merge completed that requested interval even when it contained no matching events; analytics completeness still requires contiguous completed DuckDB `ops.pipeline_runs` and successful publication. The worker wiring that invokes this contract is a separate orchestration step.

### `stg_wallets`

Configured wallet targets at `(chain_id, wallet_address)` grain. `wallet_id` is not retained because chain plus normalized address is the canonical key. The current `ens` value remains pinned project configuration for presentation and snapshot labeling; it is not live ENS-resolution evidence and is not copied into event facts. The seed may contain multiple targets. Live transfer staging still selects exactly one with `EVM_WALLET_SCAN_ADDRESS` (or requires one target when the variable is unset), and `stg_wallets` is the selected-wallet projection used for that interval. The live `pipeline_metadata` mart reads the durable target registry and retains one metadata row per target with a completed snapshot run in the current scope version, while temporarily including the current in-flight run during dbt materialization so the staged artifact has current provenance. Separate completed wallet projections remain together in the complete artifact. The static historical target is:

- `Gitcoin Schelling Point multisig`
- `0x11c24f0031b4c35e2e9353764edc61299291e0af`

### `stg_account_evidence`

In live mode, reads `analytics/artifacts/account_evidence.duckdb` at one retained pinned-block observation per `(chain_id, address)`. The historical demo reads its checked-in `account_evidence_demo.csv`, containing complete observations for all 49 eligible counterparties at safe block 25,739,638 and hash `0x4da5bc7004c57265498f2e88d86d65632b5c64c47f6143a2f1d7d6659a5fa834`. The synthetic test dataset returns an empty typed relation. The current scope fixes `chain_id = 1`. Each row preserves:

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

Raw RPC observations remain separate in `token_rpc_metadata` (or the selected fixture seed for offline builds) at one row per attempted Ethereum token address, shared by every tracked wallet. The current mainnet-only seed contract uses `token_address` as its key. That relation preserves the returned `name`, `symbol`, and `decimals` alongside `rpc_block_number`, `fetched_at`, `fetch_status`, and `error_code`. The resolved enrichment consumes complete or partial metadata and excludes failed-only attempts, but it does not copy RPC execution fields into every resolved token row. Adding a wallet can introduce new token candidates, while normal enrichment skips existing rows; explicit retry or refresh modes may query failed or selected cached rows again.

### `int_wallet_transfer_events`

Filters staged transfers to configured wallets using `(chain_id, wallet_address)` and adds:

- `direction`: `self` when both emitted participants equal the wallet, otherwise `in` when the wallet is the recipient or `out` when it is the sender. The self branch is evaluated first.
- `counterparty_address`: the other side of an inbound/outbound transfer; for a self-transfer it equals the tracked wallet so the immutable event remains self-contained and auditable.
- `counterparty_account_type` plus the complete pinned observation, fetch status, singular reason code, and evidence schema version; unenriched counterparties remain `unknown` / `not_fetched`.
- `value_raw`: the exact base-10 string emitted in the log. Token `decimals` remain adjacent sourced metadata so a future consumer can derive an amount with an explicit precision and presentation policy; the current model does not cast the raw value to floating point.
- automatic token recognition status, reason, source, and classifier version copied from token enrichment without changing the event grain.
- `transaction_sender_relation`: `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `from` and the emitted Transfer participants.
- `transaction_target_relation`: `token_contract`, `transfer_sender`, `transfer_recipient`, `other`, or `unknown`, based only on address equality between top-level transaction `to`, the emitting token, and Transfer participants.
- `is_indirect`: true for an observed `transaction_from_address != from_address`, false for an observed match, and null when transaction-sender evidence is unavailable.

This is the shared semantic event relation for all dashboard marts. It is materialized as a table
so the standalone DuckDB retains complete row-level event and enrichment evidence after the
build-only HyperIndex and account-evidence attachments are gone. Each mart selects only the fields
and grain required by its consumer directly from this relation; `wallet_events` is not an upstream
fact table for the other marts. Its exact 39-column contract omits a second event ID and stored
calendar date: consumers use the canonical composite key and derive dates from `block_timestamp`.

## Marts

### `wallet_events`

Lean application-serving event table with exactly 18 stored columns. Its grain and key are one configured-wallet event per `(chain_id, wallet_address, transaction_hash, log_index)`. It retains the block number/timestamp, transaction and log ordering identifiers, token display identity, automatic recognition status, wallet-relative direction, nullable indirect flag, counterparty address, and the four account-evidence fields rendered by the dashboard. The API and fixture exporter derive `transfer_id` as `chain_id-transaction_hash-log_index`; it is not stored as a second event identifier.

Complete immutable event evidence—including block hash, emitted participants, exact raw value, transaction envelope, relation codes, token decimals, and enrichment provenance—remains in `int_wallet_transfer_events`. The lean mart is a delivery projection, not the system-of-record event relation.

### `token_summary`

One row per wallet, emitting contract, recognition status, and counterparty account type across inbound, outbound, and self activity. The grain does not include the full account-evidence signature. This 16-column fixture-serving grain supports inclusive account filtering and is aggregated back to token grain by the fixture client before ranking. The live API derives its token ranking directly from `wallet_events` so current recognition overrides apply consistently. The mart records token display identity; total, inbound, outbound, and self captured Transfer-signature event counts; confirmed-indirect inbound and outbound counts; and distinct sender, recipient, and unioned external-counterparty address counts. Without token-standard disambiguation, these counts are ERC-20-intended rather than proven fungible-token measures.

`indirect_inbound_transfer_count` and `indirect_outbound_transfer_count` count only `is_indirect = true`. Legacy nulls are excluded rather than treated as direct or indirect, so each indirect count is bounded by its corresponding direction total.

`sender_account_count` counts distinct non-zero, non-self counterparties on inbound events. `recipient_account_count` applies the same exclusions on outbound events. `counterparty_count` is their distinct union, so it must not be calculated by adding the other two counts. These are event-address roles, not proof of human wallets or transaction initiation.

Exact raw values, token decimals, and detailed recognition/metadata provenance remain in `int_wallet_transfer_events` and `int_token_enrichment`. They are deliberately not duplicated into this serving mart because the dashboard does not consume token quantities or provenance fields.

### `counterparty_summary`

One row per wallet, chain, eligible counterparty, and recognition status. This 14-column fixture-serving mart keeps only the identity, recognition cell, account badge evidence rendered by the dashboard, event/token counts, and first/last captured timestamps. `transfer_count` is the number of captured Transfer-signature events, not a proven ERC-20-only or distinct-transaction metric; inbound and outbound event counts reconcile to that total. The live API derives counterparty rankings directly from `wallet_events` so current recognition overrides apply consistently.

The ranking-serving mart excludes the zero address, the tracked wallet itself, and any counterparty address observed as an emitting token contract in the indexed wallet dataset. These exclusions do not delete rows from `wallet_events` or alter event totals.

Detailed bytecode size, observation timestamp, fetch status, reason, and evidence-schema provenance remain in `stg_account_evidence` and `int_wallet_transfer_events`; population coverage and successful-observation bounds remain in `pipeline_metadata`.

### `timeline_daily`

Nine-column daily captured-event counts by wallet, token, recognition, counterparty account type, and direction (`in`, `out`, or `self`). The grain does not include the full account-evidence signature. This mart remains only the fixture-demo timeline source; the local API derives complete yearly or monthly event-count buckets directly from `wallet_events` so current manual recognition overrides and query predicates apply consistently. Self events remain in total counts but contribute to neither inbound nor outbound directional stacks.

Token addresses remain part of the mart grain so fixture search and token filtering stay exact. Raw values and token/recognition provenance remain in `int_wallet_transfer_events`; they are not duplicated into this count-only delivery relation.

### `pipeline_metadata`

One row per `(chain_id, wallet_address)` containing the pinned `configured_wallet_label`, fixture-versus-HyperIndex source, generation time, complete captured-event count, observed event block/time extrema, and account-evidence coverage metadata. `configured_wallet_label` is derived from the pinned `stg_wallets.ens`, falling back to the wallet address; it remains presentation configuration, not live ENS evidence. Live snapshot runs separately record the accepted input and, for ENS-shaped labels, the finalized ENS resolution provenance in `ops.pipeline_runs`. Live rows carry the completed snapshot run ID, cumulative start block, finalized end block and hash, `ethereum_finalized` policy, semantic scope version, and `envio_hyperindex` source. The historical fixture carries the same fields from its reviewed manifest, plus `mainnet-demo-snapshot-v1` and the official wallet-attribution URL. The synthetic test fixture keeps them null. Snapshot fields describe verified scan coverage; `event_block_number_min`/`max` and `first_event_at`/`last_event_at` describe only observed rows and can never establish continuity.

Account-evidence coverage uses `distinct_nonzero_nonself_event_counterparties` as its population scope. At the address grain, `eligible = classified + failed + not_checked`; the event-weighted fields apply the same statuses to captured Transfer-signature rows. Rates are deliberately not stored because they are exactly derivable from these reconciled counts. Observation block/time bounds and the schema version are derived only from successfully classified addresses. The historical fixture reports all 49 eligible addresses as classified with pinned observation provenance, while the synthetic test fixture reports its population as not checked.

The mart does not store token, counterparty, recognition, timeline-cell, or other delivery-shape counts. The fixture exporter projects the mart fields explicitly, calculates complete and returned counts from each relation it actually delivers, and enriches `meta.json` with `dashboard-export-v1`, limits, and sampling state. It accepts only `mainnet-demo-snapshot-v1`, sets `completeness_scope: finalized_block_range` and `finality_status: finalized`, and keeps observed event extrema separate from the recorded scan boundary.

## Operational and application-owned local state

These tables are created and owned by Python application/orchestration code rather than dbt, so they do not appear in the generated dbt catalog. Their exact physical column order, types, nullability, and keys are enforced by Python tests alongside the owning DDL.

### `account_evidence.account_evidence`

The ignored `analytics/artifacts/account_evidence.duckdb` cache is attached read-only under the `account_evidence` catalog during live dbt builds. Its grain and primary key are one retained observation per `(chain_id, address)`, shared across every tracked wallet. Successful observations are preserved; failed attempts can be replaced by a later successful result. A new wallet reuses successful observations for counterparties already present in this cache and only collects addresses without a successful observation; failed observations remain retryable.

| Column | Physical contract | Semantics |
| --- | --- | --- |
| `chain_id` | `INTEGER NOT NULL`, primary key | EVM chain identifier; constrained by the collector to Ethereum mainnet. |
| `address` | `VARCHAR NOT NULL`, primary key | Lowercase observed account address. |
| `account_type` | `VARCHAR NOT NULL` | `eoa_candidate`, `contract`, or retryable `unknown`. |
| `code_state` | `VARCHAR NOT NULL` | `no_code`, `eip7702_delegated`, `contract_code`, or `unknown`. |
| `code_size_bytes` | nullable `BIGINT` | Exact observed bytecode size; null when no usable response exists. |
| `observation_block_number` | `BIGINT NOT NULL` | Concrete block used for `eth_getCode`. |
| `observation_block_hash` | nullable `VARCHAR` | Canonical hash for that block. The storage column remains nullable for historical compatibility, but the current collector always writes it and `stg_account_evidence` requires it. |
| `observation_block_timestamp` | `TIMESTAMPTZ NOT NULL` | UTC chain timestamp of the observation block. |
| `eip7702_delegation_target` | nullable `VARCHAR` | Exact lowercase target decoded only from 23-byte EIP-7702 delegation code. |
| `fetch_status` | `VARCHAR NOT NULL` | `complete` or retryable `failed`. |
| `reason_code` | `VARCHAR NOT NULL` | Singular machine-readable explanation for the classification or failure. |
| `finality_policy` | `VARCHAR NOT NULL` | `safe` or the explicit confirmed-head fallback used to pin the block. |
| `evidence_schema_version` | `VARCHAR NOT NULL` | Account-evidence contract version, currently `account-evidence-v2`. |
| `fetched_at` | `TIMESTAMPTZ NOT NULL` | UTC pipeline time when the RPC attempt completed. |

### `ops.pipeline_runs`

Live orchestration owns `ops.wallet_targets` at exactly one durable row per `(chain_id, wallet_address)`, with that composite key and no synthetic target identity. It also owns `ops.scan_generations` at one wallet-scoped finalized interval, canonical end hash, scope, and lifecycle status per attempted wallet snapshot. A generation and its `pipeline_runs` row never coordinate or imply continuity for another wallet.

The live build wrapper creates this table inside `analytics/artifacts/live.duckdb`; dbt does not model, seed, replace, or export it. Its grain is one attempted run for `(chain_id, wallet_address, scope_version, from_block, to_block)`, identified by `run_id`. A failed run whose raw ingestion checkpoint is complete is reopened and reused for publication retry; failures before that checkpoint remain auditable and retryable. `wallet_label` is derived from the pinned configured ENS value, falling back to the wallet address; the separate input/provenance fields below record any finalized ENS resolution.

| Column | Physical contract | Semantics |
| --- | --- | --- |
| `run_id` | `VARCHAR NOT NULL`, primary key | UUID identifying one attempted run. |
| `chain_id` | `INTEGER NOT NULL` | EVM chain identifier, constrained to `1`. |
| `generation_id` | `VARCHAR NOT NULL` | UUID identifying the wallet-scoped scan generation for this attempted snapshot. |
| `wallet_address` | `VARCHAR NOT NULL` | Lowercase configured wallet scanned by the run. |
| `wallet_label` | `VARCHAR NOT NULL` | Pinned project display label; not itself a live ENS-resolution claim. |
| `from_block` | `BIGINT NOT NULL` | Inclusive interval start. |
| `to_block` | `BIGINT NOT NULL` | Inclusive finalized interval end. |
| `to_block_hash` | `VARCHAR NOT NULL` | Lowercase canonical hash pinned for `to_block`. |
| `events_found` | nullable `BIGINT` | Matching captured-event count; populated only when the run completes successfully. |
| `status` | `VARCHAR NOT NULL` | `running`, `completed`, or `failed`. |
| `completed_at` | nullable `TIMESTAMPTZ` | UTC pipeline completion/failure time; null while running. |
| `scope_version` | `VARCHAR NOT NULL` | Version of the indexed semantic scope. |
| `original_input` | `VARCHAR NOT NULL` | Exact user/configuration input accepted at scan start. |
| `normalized_name` | nullable `VARCHAR` | Lowercase conservative ASCII ENS name; null for direct addresses. |
| `resolver_source` | `VARCHAR NOT NULL` | `direct-address` or the pinned ENS registry plus the resolver address used. This is dependency provenance, not a trust claim. |
| `observation_block_number` | `BIGINT NOT NULL` | Finalized Ethereum block at which the input was resolved or directly observed. |
| `observation_block_hash` | `VARCHAR NOT NULL` | Canonical hash for `observation_block_number`. |
| `observation_timestamp` | `TIMESTAMPTZ NOT NULL` | UTC block timestamp for the finalized observation. |
| `ingestion_status` | `VARCHAR NOT NULL` | `pending` until durable raw HyperIndex ingestion is acknowledged; then `completed`. This is independent of analytics publication. |
| `raw_events_found` | nullable `BIGINT` | Count observed during the durable raw-ingestion checkpoint. |
| `raw_ingested_at` | nullable `TIMESTAMPTZ` | UTC time when durable raw ingestion was acknowledged. |

The first interval starts at HyperIndex `_meta.startBlock`. Only completed, exactly contiguous intervals advance each wallet's next start to that wallet's previous `to_block + 1`; failed rows remain auditable and retryable. The target is the newest block that is both fully processed by HyperIndex and no newer than Ethereum's current `finalized` head, capped by a configured HyperIndex end when present. Its canonical hash is fetched from Ethereum RPC. Durable raw ingestion is acknowledged before publication begins. If publication fails after that acknowledgement, a retry reopens the same failed run and interval instead of creating a new ingestion attempt; if ingestion is still pending, the failed interval remains retryable through the normal orchestration path. A run becomes `completed` only after dbt succeeds. During a live dbt build, `pipeline_metadata` selects each wallet's latest completed run in the current scope independently, plus the current in-flight run for the wallet being built, so one wallet's generation cannot supply another wallet's provenance and wallets may temporarily have different finalized coverage ends. The manager publishes only after the worker succeeds and the run is completed. Rebuilding transformations while already current reuses each wallet's latest completed run rather than creating a false scan interval.

When an older artifact is opened, the additive schema migration keeps legacy rows readable with
`legacy-configured-wallet` provenance and their recorded snapshot end block/hash; only new runs
carry exact ENS observation provenance. A new live build resolves its configured input before it
creates a run; an explicit scan job resolves its input before handing the typed provenance to the
worker adapter, which is responsible for persisting it in the output artifact.

Scan input resolution is a server-side boundary before a live run is created or a scan worker is
started. It accepts a canonical
Ethereum address or a conservative lowercase ASCII ENS name, uses the pinned Ethereum ENS registry
address `0x00000000000c2e074ec69a0dfb2997ba6c7d2e1e`, and calls both registry `resolver(bytes32)` and
resolver `addr(bytes32)` at one finalized observation block. For live dbt builds, the original input,
normalized name, resolved address, registry/resolver source, block number/hash, and block timestamp
are copied into the same `ops.pipeline_runs` row. Scan jobs carry the same typed fields across the
explicit worker adapter; the manager does not create a run or claim combined artifact persistence.
Invalid, unsupported, or unresolved names raise an
`ENSNotRecognizedError` before a wallet can become an index target. No separate database is used.

### `app.token_recognition_overrides`

The local API creates this table inside `analytics/artifacts/live.duckdb`; dbt does not model, seed, replace, or export it. Its grain and primary key are `(chain_id, token_address)`.

| Column | Physical contract | Semantics |
| --- | --- | --- |
| `chain_id` | `INTEGER NOT NULL`, primary key | EVM chain identifier, constrained to `1`. |
| `token_address` | `VARCHAR NOT NULL`, primary key | Lowercase emitting contract address present in the current snapshot. |
| `status` | `VARCHAR NOT NULL` | Manual `recognized` or `other` result. |
| `updated_at` | `TIMESTAMPTZ NOT NULL`, defaults to current time | UTC time of the latest manual mutation. |

A row overrides automatic `wallet_events.recognition_status`; no row means automatic classification. Normal in-place dbt builds preserve the table, and the scan-job artifact swap copies it into the staged artifact before replacement. Explicitly deleting the DuckDB file loses this local-only state.

## Local API contract

The API accepts an optional `wallet_address` on every dashboard query endpoint; clients may select a configured target by its canonical lowercase address. When omitted, the service resolves the active target from request-time `EVM_WALLET_SCAN_ADDRESS` or the artifact's sole current metadata row. Zero or multiple metadata wallets fail clearly and require the environment selector; no live wallet is hardcoded. Static demo data uses only the attributed historical Gitcoin target documented above; the synthetic target remains test-only.


The `/api/v1` service currently advertises response schema `dashboard-api-v16`. It serves only `analytics/artifacts/live.duckdb` in production mode and refuses fixture provenance, missing/unfinalized snapshot metadata, a metadata run ID that does not match the latest completed `ops.pipeline_runs` row, non-contiguous completed intervals, or a cumulative run event count that does not reconcile with `pipeline_metadata.transfer_count`. It projects the metadata contract explicitly rather than exposing every mart column. It left-joins the application-owned override table before recognition, repeated inclusive `account`, optional literal `q`, and optional UTC date predicates are applied. Search covers the identifiers and labels exposed by the dashboard: transaction hash, configured wallet, counterparty, token address, token symbol, and token name. `start` is inclusive and `end` is exclusive; they are `YYYY-MM-DD` dates and must be provided together with `start < end`. Omitting `account` selects all rows, including internal unresolved evidence; `account=eoa_candidate` or `account=contract` selects only that successfully classified type. `account=none` explicitly selects no rows and cannot be combined with another account value. For counterparty rankings, recognition selects an inclusive address cohort: an address qualifies when at least one scoped event has the selected recognition status, then all of that address's events inside the remaining account/search/time scope contribute to its counts. This preserves mixed recognized/other relationships instead of splitting or dropping them. Version 16 renames the pinned label, removes obsolete and derivable metadata fields, and sources observed event block extrema directly from the mart. The API derives event `transfer_id` at delivery time and uses transaction index in its stable event cursor. Exact raw values remain only in the complete intermediate event relation and are not published to the current dashboard. Counterparty counts remain external-only. The service exposes:

- `GET /health/live`: process liveness only; `200 {"status":"ok"}` does not claim that an analytics artifact has been published;
- `GET /health`: artifact-aware readiness and provenance for the currently selected live wallet;
- `GET /scan-jobs/active`: the one queued or running process-local job, or `null`, for local client
  activity recovery; it is not durable scan history;

- `metadata`: one provenance object for the configured wallet, including DuckDB generation time, contiguous finalized snapshot bounds, observed event block/time extrema, account-evidence coverage, `finality_status`, and API schema version. Event extrema remain separate from the indexer checkpoint;
- `summary`: one exact aggregate for the active selection, with transfer, distinct-token, distinct-counterparty, block, and event-time bounds;
- `events`: one row per immutable `wallet_events` row, ordered newest-first by block/transaction/log position and traversed with an opaque keyset cursor;
- `timeline`: one complete, gap-filled UTC series with exact total, inbound, outbound, and self captured-event counts; each bucket reconciles as `total = inbound + outbound + self`. `interval=year` returns the stable observed-year domain; `interval=month` requires one `year` and returns only that calendar window through the latest observed month when it is the boundary year. Recognition, account, and search filters can zero a bucket but do not remove its calendar position;
- `tokens`: one exact aggregate per emitting token contract, ranked after filtering and limited only after aggregation;
- `PUT /tokens/{token_address}/recognition`: persist `recognized` or `other`, returning the previous override so a client can undo exactly;
- `DELETE /tokens/{token_address}/recognition`: remove the override and return to the automatic result;
- `counterparties`: one exact aggregate per eligible address, with the same zero/self/emitting-token exclusions as the mart ranking, ranked by captured Transfer-signature event count after inclusive cohort selection;
Event responses distinguish `complete_matching_count` from `returned_count`, `limit`, `next_cursor`, and `is_paginated`. Ranked responses distinguish the complete matching item count from the returned top-N and `is_truncated`. Timeline `complete_matching_count` is the sum of exact captured-event counts while `returned_count` is the number of gap-filled buckets. `is_sampled` is always false because no matching source rows are randomly or permanently discarded. A top-N ranking is a bounded presentation over a complete calculation, not a sample.

The React live adapter sends the same recognition, account, and search predicates to every endpoint, displays summary counts from the complete matching set, and distinguishes those totals from bounded token, counterparty, and event rows. `All years` requests yearly buckets without a date predicate. Selecting a year—through the dropdown or its bar—requests that year's monthly buckets while sending its exact half-open UTC range to summary, event, token, and counterparty requests. Selecting a month narrows those endpoints again; clearing the month returns to the selected year, while `All years` clears the time scope. The timeline request omits the active date predicate so all buckets in the current navigation scope remain available. Event expansion follows `next_cursor`; it never infers completeness from the current browser array. The static adapter remains separate, reads only generated fixture JSON, permits year/month timeline navigation, and does not claim that its bounded rows support dashboard period cross-filtering.

The fixture exporter records exact transfer/token/counterparty statistics for the nine combinations of three non-empty recognition selections and three non-empty EOA/Contract selections. The full account selection includes unresolved internal rows. Live serving computes only the requested selection.

## Tests

dbt tests enforce:

- No duplicate staged transfer logs at canonical `(chain_id, transaction_hash, log_index)` grain.
- An exact 16-relation `main`-schema inventory, including each relation's table/view materialization, so retired or accidentally introduced analytics relations cannot remain hidden in an existing DuckDB artifact.
- Exact physical column, type, nullability, and key contracts for the Python-owned account-evidence, snapshot-run, and recognition-override tables.
- Non-null wallet, counterparty, and token addresses in dashboard marts.
- Valid `direction` values.
- Valid metadata-availability values throughout enrichment and serving models.
- Valid automatic `recognized`/`other` values and `token-recognition-v1` provenance, plus persistent API override precedence and reset behavior.
- Null snapshot claims for the synthetic test dataset and complete, internally ordered finalized snapshot fields for live and historical-demo builds.
- Exact reconciliation of pipeline event counts and block/time extrema with both the semantic event relation and lean delivery relation.
- Manual recognition override precedence and `other` fallback behavior.
- Exact preservation of a maximum `uint256` raw event value through staging, the complete intermediate event relation, and token-summary aggregation.
- Valid, unique pinned-block RPC snapshots and RPC metadata precedence.
- Counterparty-summary totals that reconcile with inbound plus outbound counts, with ranking exclusions enforced.
- Exact transaction sender/target relation derivation, nullable legacy behavior, and indirect direction aggregates.
- Valid account-type/code-state precedence, exact 23-byte EIP-7702 evidence, and pinned observation/coverage consistency.
- Exact EIP-7702 code remains internal code state under an EOA-candidate primary type.
- Successful cached observations cannot be overwritten automatically, while failed code reads remain retryable.
- Fixture builds contain no account-evidence rows and keep their provenance bounds null.
- Fixture builds retain more than one event page, a five-year/month navigation domain, all three directions, direct/indirect/unknown sender evidence, both recognition states, and an empty account-evidence relation.
- The fixture export's nine recognition/address-evidence token and counterparty candidate unions plus client aggregation from account cells back to displayed token and timeline grains.
