# Operations

## Local Setup

```sh
bun install
bun run analytics:build
bun run export:dashboard
bun run dashboard:dev
```

`analytics:build` bootstraps Python dbt dependencies from `analytics/requirements.txt` if dbt is not installed in the active Python environment.

Copy `config.example.yaml` to the git-ignored `config.yaml` for one local configuration file, or use the variable names from `.env.example`. Shell environment values take precedence over YAML. Envio and dbt wrappers load the shared configuration without printing secrets.

```yaml
envio:
  api_token: ""
analytics:
  hyperindex_postgres_dsn: ""
ethereum:
  rpc_url: ""
  public_rpc_url: "https://ethereum-rpc.publicnode.com"
  account_evidence:
    erc4337_start_block: ""
```

## Fixture Mode

Fixture mode is the default so the project can be built and tested without a live HyperIndex Postgres database.

```sh
bun run analytics:build
```

The six fixture transfer rows live in `analytics/seeds/raw_erc20_transfers_fixture.csv`. They cover direct, indirect, and legacy-unknown transaction-envelope evidence while preserving emitted Transfer fields. Their separate observed-at account-evidence fixture covers all six primary types and includes one address that is both verified Safe and observed through ERC-4337. Wallet and token seeds live in `analytics/seeds/wallets.csv` and `analytics/seeds/token_metadata.csv`. Exported `meta.json` records `data_source: fixture`, and the dashboard displays a fixture badge. After changing fixture columns, use `python3 scripts/run_dbt.py build --full-refresh` once so dbt recreates the seed schema.

## Token Registry

Ordinary analytics builds use the checked-in registry without internet access. Refresh it explicitly with:

```sh
bun run labels:sync
```

The command validates Ethereum addresses and decimals, fails on cross-source decimal conflicts, and rewrites `analytics/seeds/token_metadata.csv` plus `token_metadata_manifest.json`. Naming precedence is Trust Wallet, Uniswap, then CoinGecko; manual entries in `token_label_overrides.csv` override every generated source.

Each reviewed manual `trusted` approval or `spam` entry must include a reason and evidence URL. Suspected spam is automated rather than manually assigned. Unknown tokens should be left unlisted and will receive `unknown` quality plus `unverified` status automatically; CoinGecko absence never implies spam. After a seed schema change, run one migration build with `python3 scripts/run_dbt.py build --full-refresh`; routine registry content refreshes use the normal build command.

## Spam Classification

Classification runs during every dbt build and makes no network calls. Inspect contract-level evidence in `int_token_reputation`, wallet-token behavior in `int_wallet_token_interactions`, and the effective event status in `wallet_events`. Scores, reason codes, and classifier versions are exported to the dashboard; hovering a suspected badge displays the evidence.

The Status menu independently controls visibility for `trusted`, `unverified`, `suspected_spam`, and reviewed `spam`; trusted and unverified are selected by default. The separate Quality menu defaults to `high_confidence`, while `listed` and `unknown` remain selectable. To change a threshold or reason rule, update the corresponding model, its version string, dbt tests, and `docs/architecture.md` in the same change.

## RPC Metadata Enrichment

Process the next top 100 unverified contracts by complete wallet transfer count:

```sh
bun run labels:enrich --limit 100
```

The command uses `ETHEREUM_RPC_URL`, then `ethereum.rpc_url` from `config.yaml`, then the configured public fallback. It verifies Ethereum mainnet, pins one block, batches read-only calls, and writes `analytics/seeds/token_rpc_metadata.csv`. Provider URLs are never written to output or logs.

```sh
bun run labels:enrich --limit 100 --retry-failed
bun run labels:enrich --limit 100 --refresh
```

Normal mode skips every attempted contract and advances to the next batch. Retry mode selects failed rows; refresh mode rereads ranked contracts and replaces their snapshot rows. Empty, reverting, malformed, or optional ERC20 methods remain null. RPC names and symbols are self-declared and do not promote trust.

## Counterparty Account Evidence

Collect pinned account evidence for the next 500 high-activity counterparties:

```sh
bun run addresses:enrich --limit 500
```

The command ranks eligible counterparties by complete ERC-20 transfer count, verifies Ethereum mainnet, pins one block and timestamp, and writes `analytics/seeds/counterparty_code_metadata.csv` atomically. It batches `eth_getCode`, Safe storage/interface reads, and filtered `UserOperationEvent` lookups against the versioned canonical EntryPoints in `account_evidence_manifest.json`. The manifest pins each Ethereum deployment block and transaction. The log scan clamps each EntryPoint to its deployment block, groups sender topics, and splits the remaining range into bounded chunks instead of issuing one full-history request per address. It uses the same `ETHEREUM_RPC_URL` / `config.yaml` / public-fallback precedence as token enrichment.

By default, ERC-4337 evidence coverage begins at the earliest indexed ERC-20 event block and ends at the pinned observation block. Override the lower bound only when the intended coverage is explicit:

```sh
bun run addresses:enrich --limit 500 --erc4337-start-block 17000000
```

The equivalent configuration is `ethereum.account_evidence.erc4337_start_block` or `ACCOUNT_EVIDENCE_START_BLOCK`. The requested lower bound is distinct from per-EntryPoint effective coverage because an EntryPoint cannot be checked before its deployment. A positive result proves only that the address appeared as a canonical EntryPoint event sender in a recorded successful range. A negative result is bounded by merged effective coverage and fetch status; it never silently includes a failed chunk.

The default work unit is 100,000 blocks by 50 sender topics with two retries per failed chunk. Providers with smaller limits can override these values without changing the evidence semantics:

```sh
bun run addresses:enrich --limit 500 \
  --erc4337-block-chunk-size 10000 \
  --erc4337-address-batch-size 25 \
  --erc4337-max-retries 3
```

Use `ethereum.account_evidence.erc4337_block_chunk_size`, `erc4337_address_batch_size`, and `erc4337_max_retries`, or the corresponding `ACCOUNT_EVIDENCE_BLOCK_CHUNK_SIZE`, `ACCOUNT_EVIDENCE_ADDRESS_BATCH_SIZE`, and `ACCOUNT_EVIDENCE_MAX_RETRIES` environment variables. Successful chunks are retained across in-process retries. If a chunk still fails, every affected address records that exact EntryPoint/range in `erc4337_failed_ranges`, retains the other successful ranges in `erc4337_effective_coverage`, and receives `fetch_status = partial`. A failed code lookup is also `partial` when successful EntryPoint coverage or a positive sender event remains usable; `failed` is reserved for no usable source evidence.

```sh
bun run addresses:enrich --limit 500 --retry-failed
bun run addresses:enrich --limit 500 --refresh
```

Normal mode advances to unattempted addresses, retry mode retries `failed` and `partial` checks, and refresh mode rechecks ranked addresses at a new pinned block. Run the live analytics build and dashboard export after enrichment. A seed-schema migration requires `python3 scripts/run_dbt.py build --full-refresh` once for an existing DuckDB file.

Rows migrated from the earlier code-only snapshot are retained with `coverage_scope = legacy_code_snapshot`, explicit `safe_not_checked` / `erc4337_not_checked` reasons, and `fetch_status = partial`. They preserve the prior pinned code observation without implying that the newer Safe or EntryPoint evidence was collected. Refresh only the desired ranked batch to replace them; this migration does not perform a full live enrichment.

Interpretation rules are intentionally strict:

- `eoa_candidate` means no code was observed at the pinned block; it does not prove EOA status, control, personhood, or permanence.
- `eip7702_delegated` requires exact `0xef0100 || 20-byte target` code.
- `safe` requires an official mainnet singleton/deployment match and consistent `getOwners()` / `getThreshold()` results. Interface-only matches remain contract evidence.
- `erc4337_account` requires positive `UserOperationEvent.sender` evidence from a checked-in versioned canonical EntryPoint.
- Safe and ERC-4337 remain independent flags even though one primary account type is selected by precedence.

This is an explicit, potentially RPC-intensive ranked batch operation. Fixture builds and ordinary dbt runs never invoke it, and this change does not perform a full live refresh.

## HyperIndex Mode

Run the indexer locally:

```sh
bun run indexer:dev
```

Local HyperIndex requires Docker and an `ENVIO_API_TOKEN`. The indexer uses Envio wildcard indexing with topic filters for the configured wallet and writes `Erc20Transfer` entities to Postgres. Its event field selection includes top-level transaction `from` and `to`; the entity columns are nullable so existing rows can remain readable during migration. Raw event duplication is disabled.

Run `bun run indexer:codegen` after changing the Envio field selection or entity schema. Adding the nullable columns does not retroactively populate already-processed entities: use the appropriate Envio replay/reindex procedure for the intended block range before claiming complete transaction-initiation coverage. Until replay, dbt preserves missing senders/targets as null, relation evidence as `unknown`, and `is_indirect` as null. A normal fixture build, export, or dashboard run never starts that backfill.

After the indexer has created and populated `public."Erc20Transfer"`, export its Postgres connection URI and build in live mode:

```sh
export DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN='postgresql://USER:PASSWORD@127.0.0.1:PORT/DATABASE'
bun run analytics:build:hyperindex
bun run export:dashboard
```

dbt-duckdb attaches that database read-only as the `hyperindex` catalog. The wrapper stops with a clear error when live mode is requested without the DSN. Confirm the mapped local port with `docker port envio-postgres 5432`; this project currently maps it to `5433`. Store the URI under `analytics.hyperindex_postgres_dsn` in ignored `config.yaml` to avoid exporting it in every shell.

## Export

```sh
bun run export:dashboard
```

This creates:

- `public/data/graph.json`
- `public/data/summaries.json`
- `public/data/timeline.json`
- `public/data/events.json`
- `public/data/meta.json`

The JSON is bounded for static-browser performance: up to 1,000 newest events, 250 top graph interactions, and 5,000 daily timeline rows per status-quality-account-evidence cell. Event rows preserve raw Transfer participants, event block/time, nullable top-level transaction evidence, the indirect marker, and observed-at account evidence. Token and counterparty exports take exact candidate unions across all 6,615 non-empty status-quality-account selections, then include every account cell for the selected top-500 tokens and top-50 counterparties. Browser filtering aggregates token and timeline cells back to their displayed grains. Files are replaced atomically so readers never observe partially written JSON. The complete transformed data remains in `analytics/wallet_analytics.duckdb`. Inspect `meta.json` for exact-ranking guarantees, selection/candidate counts, account-evidence min/max observation range and scan coverage, complete/exported row counts, per-cell limits, and `is_sampled` before publishing or debugging a dashboard snapshot. `is_sampled` describes overall export completeness; it does not invalidate the separately proven ranking candidate unions.

## Verification

```sh
bun run test
```

The full test command builds analytics, exports JSON, runs JS tests, and runs dbt tests.

## GitHub CI and Deployment

`.github/workflows/ci.yml` runs the reproducible fixture pipeline and production dashboard build for pull requests and pushes to `main`. It also runs advisory JavaScript and Python dependency audits. The uploaded production build is retained for one day to help diagnose a run; this retention setting does not control how long a deployed site stays online.

`.github/workflows/deploy.yml` rebuilds the exact revision that passed `main` CI and publishes it to GitHub Pages. Deployment is disabled by default. To enable it when the repository and GitHub plan support Pages:

1. Set the repository Actions variable `ENABLE_GITHUB_PAGES` to `true`.
2. In repository Pages settings, select GitHub Actions as the source if GitHub does not configure it automatically.
3. Run the Deploy workflow manually once, or merge a change into `main` and let successful CI trigger it.

The site does not expire after one day; only the separate CI download artifact does. If private-repository Pages is unavailable on the current plan, keep the gate disabled and connect the private repository to a host that supports private Git integration, such as Cloudflare Pages, Netlify, or Vercel. No dashboard code change is required for a root-domain deployment; set the host's build command to `bun run test && bun run dashboard:build` and its output directory to `dist`.

Dependabot checks Actions, JavaScript, indexer, and Python dependencies weekly. Pull requests inherit the repository template and Copilot review instructions, but branch protection and automatic Copilot review assignment are repository settings and must be enabled separately when desired.

## Local Codex Review

Run `bun run hooks:install` once per clone to set this repository's `core.hooksPath` to `.githooks`. The pre-commit hook delegates to `scripts/codex_review_gate.sh`, which starts a new ephemeral Codex process with a read-only sandbox and no approval prompts. The reviewer is instructed to inspect only the staged diff and emits JSON matching `.codex/review-output.schema.json`; the wrapper validates that response before allowing the commit.

This is an advisory AI review promoted to a local gate, not a proof of correctness. It adds network latency and consumes Codex usage, so the deterministic test suite and remote CI remain required. The hook fails closed when Codex, Bun, authentication, or connectivity is unavailable. Use `SKIP_CODEX_REVIEW=1` only as an explicit one-commit escape hatch; the bypass is visible in the terminal but is not recorded in Git history.
