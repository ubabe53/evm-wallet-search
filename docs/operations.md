# Operations

## Local Setup

```sh
bun install
bun run indexer:dev
bun run analytics:build:hyperindex
```

This is the primary local-product data path. `analytics:build:hyperindex` bootstraps Python dbt dependencies from `analytics/requirements.txt` if dbt is not installed in the active Python environment, reads HyperIndex `_meta` through its local GraphQL endpoint, and resolves Ethereum's `finalized` head through RPC. Its target is the newest block covered by both transactional indexer progress and finality, capped by a configured HyperIndex end when present. It pins that target's canonical hash, reads the entity table only through the target, and builds the DuckDB marts in `analytics/artifacts/live.duckdb`.

Before a scan job is created, the server-side scan-input boundary accepts either an address or an
ENS name. ENS names use the pinned mainnet ENS registry and standard resolver calls at one
Ethereum `finalized` observation block. The scan run records the original input, normalized name,
resolved address, resolver source, observation block number/hash, and block timestamp in
`ops.pipeline_runs`. Unsupported or unresolved names fail with `ENSNotRecognizedError` and are
never passed to the indexer. This is provenance in the existing live artifact, not a third
database, and it does not implement a reindex worker.

Start the local API after the live build:

```sh
bun run api:dev
```

The service binds only to `127.0.0.1:8000`, refuses fixture provenance, and exposes readiness at `/api/v1/health` plus interactive OpenAPI documentation at `/docs`. It owns short-lived DuckDB connections and may write only `app.token_recognition_overrides`. Stop the API before rebuilding `live.duckdb`; the dbt writer and application process must not access the same file concurrently. Normal in-place builds preserve overrides because dbt does not own the `app` schema, and the scan-job artifact swap copies the application-owned table into the staged artifact before replacement. Explicitly deleting `live.duckdb` still removes them. Restart the API and reload the dashboard after a successful live build so every request and the browser's snapshot metadata use the new artifact.

In a second terminal, run `bun run dashboard:dev`. Vite selects the live API adapter and proxies `/api` to `127.0.0.1:8000`; it does not load `public/data`. Fixture and live dbt artifacts are isolated, so deterministic validation cannot replace the live database.

Copy `config.example.yaml` to the git-ignored `config.yaml` for one local configuration file, or use the variable names from `.env.example`. Shell environment values take precedence over YAML. Envio and dbt wrappers load the shared configuration without printing secrets.

```yaml
envio:
  api_token: ""
analytics:
  hyperindex_postgres_dsn: ""
  hyperindex_graphql_url: "http://127.0.0.1:8080/v1/graphql"
ethereum:
  rpc_url: ""
  public_rpc_url: "https://ethereum-rpc.publicnode.com"
  account_evidence:
    batch_size: 100
    max_retries: 2
    fallback_confirmations: 64
```

## Fixture Demo Mode

Fixture mode exists for deterministic tests and the eventual GitHub Pages portfolio demo. It is not the primary local application mode and does not stand in for HyperIndex verification.

```sh
bun run analytics:build:fixture
```

The seven fixture transfer rows live in `analytics/seeds/raw_transfer_events_fixture.csv`. They cover direct, indirect, self-transfer, and legacy-unknown transaction-envelope evidence while preserving emitted Transfer fields and canonical block hashes. There is no account-evidence fixture: the fixture build uses an empty typed relation, so it never invents address classifications. Wallet and token seeds live in `analytics/seeds/wallets.csv` and `analytics/seeds/token_metadata.csv`. Fixture builds write `analytics/artifacts/fixture.duckdb`, remove any live Postgres DSN from the dbt child process, and never attach HyperIndex. Exported `meta.json` records `data_source: fixture`, and the demo displays a fixture badge.

`bun run analytics:build` remains an alias for `analytics:build:fixture` so existing CI and contributor commands stay deterministic. The exporter reads only the fixture database and may overwrite only the ignored files under `public/data/`.

## dbt Data Catalog

Generate the deterministic field-level catalog after building the fixture artifact:

```sh
bun run analytics:docs:generate
```

This runs `dbt docs generate`, then fails if any project model, seed, source, or catalog column lacks a description, or if a resource omits its grain, primary key, provenance, or consumers. The generated catalog under `analytics/target/` is ignored build output; the reviewed source of truth is the layer-owned YAML in `analytics/models/`, `analytics/seeds/_seeds.yml`, and the reusable semantic definitions in `analytics/docs/data_contracts.md`. The Python-owned account-evidence, snapshot-run, and recognition-override tables sit outside dbt's manifest; their structured contracts live in `docs/data-model.md` and their exact physical schemas are enforced by the owning Python tests.

Inspect the catalog locally at `http://127.0.0.1:8081`:

```sh
bun run analytics:docs:serve
```

The supported documentation workflow always uses the deterministic fixture artifact and strips any ambient HyperIndex DSN. It documents the same schemas, lineage, materializations, and semantic contracts used by live builds, but its catalog row counts and observed values are fixture data—not live freshness or finalized coverage evidence. Stop the server with Ctrl-C. Use `bun run analytics:docs:check` in automation when the fixture artifact has already been built.

## Token Registry

Ordinary analytics builds use the checked-in registry without internet access. Refresh it explicitly with:

```sh
bun run tokens:refresh
```

`labels:sync` remains an alias. The command downloads Trust Wallet, Uniswap, CoinGecko, and online Coinbase Exchange Ethereum contract entries; validates exact Ethereum addresses and available token decimals; fails on cross-source decimal conflicts; and rewrites `analytics/seeds/token_metadata.csv` plus `token_metadata_manifest.json`. Naming precedence is Trust Wallet, Uniswap, CoinGecko, then Coinbase. Coinbase trading precision is not used as token decimals, so a Coinbase-only row may have unknown decimals. Manual entries in `token_label_overrides.csv` override every generated source.

Each reviewed manual `recognized` or `other` entry must include a reason and evidence URL. Any exact-address source match is automatically `recognized`; unmatched tokens are `other`. The tiny `wallets` configuration seed is always recreated by a normal build. After changing another seed's column schema, run one migration build with `python3 scripts/run_dbt.py build --full-refresh`; routine registry content refreshes use the normal build command.

## Token Recognition

Recognition resolution runs during every dbt build and makes no network calls. Before building, dbt idempotently removes every known retired `main`-schema analytics relation. The completed build then validates the exact current 16-relation inventory and each relation's table/view materialization, so legacy graph, reputation, and superseded staging objects cannot survive unnoticed in an existing artifact. The cleanup never targets the separately owned `ops`, `app`, or account-evidence schemas.

The dashboard defaults to `All` and offers `Recognized` and `Other` filters. Live mode also permits a per-token `Automatic`, `Recognized`, or `Other` choice; it persists the override in `app.token_recognition_overrides` and offers Undo for four seconds. The fixture demo renders these controls read-only.

## RPC Metadata Enrichment

Process the next top 100 `other` contracts by complete wallet transfer count:

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

Collect pinned code evidence for every unresolved event counterparty:

```sh
bun run addresses:enrich
```

The command selects distinct `wallet_events.counterparty_address` values, excluding the configured wallet and zero address. It verifies Ethereum mainnet, resolves one concrete `safe` block, and passes that block number to every `eth_getCode`. If the provider does not support the `safe` tag, it pins `latest` minus the configured confirmation buffer. Block number, hash, timestamp, finality policy, and fetch time are stored with every result.

The ignored `analytics/artifacts/account_evidence.duckdb` cache is checkpointed after every JSON-RPC batch. Successful rows are never selected or overwritten automatically; failed or malformed results stay `unknown` and are retried by a later invocation. The default run has no address limit. `--limit` exists only for an intentional partial run.

Before reusing this cache after a clean indexer replay, run
`bun run analytics:build:hyperindex`. Its `stg_account_evidence` contract checks include
`analytics/tests/valid_account_evidence.sql`. Archive and recreate the cache when those checks
reject legacy rows; do not relabel or coerce them into current pinned-block evidence. An empty
cache is valid and makes coverage report the current counterparty population as `not_checked`
without starting an implicit 100k-plus RPC enrichment.

After the next live analytics build, `pipeline_metadata` recomputes coverage against the current snapshot rather than counting every row in the cache. It reports distinct eligible, classified, failed, and not-checked nonzero/nonself counterparties plus the same reconciliation weighted by captured Transfer-signature events. This makes an intentional `--limit` run visibly partial. Cached addresses that are no longer in the current wallet population do not count toward coverage.

The default work unit is 100 `eth_getCode` calls with two retries for unresolved calls. Providers with smaller limits can override these values without changing the evidence semantics:

```sh
bun run addresses:enrich --limit 500 \
  --batch-size 50 \
  --max-retries 3 \
  --fallback-confirmations 96
```

Use `ethereum.account_evidence.batch_size`, `max_retries`, and `fallback_confirmations`, or `ACCOUNT_EVIDENCE_BATCH_SIZE`, `ACCOUNT_EVIDENCE_MAX_RETRIES`, and `ACCOUNT_EVIDENCE_FALLBACK_CONFIRMATIONS`. Batching reduces HTTP overhead but does not remove the underlying state lookups. Very large batches can exceed provider payload or timeout limits.

Run `bun run analytics:build:hyperindex` after enrichment so dbt reads the cache and rebuilds the live marts, then restart the local API. Ordinary dbt and fixture commands never invoke the RPC collector.

Interpretation rules are intentionally strict:

- `eoa_candidate` means no code was observed at the pinned block; it does not prove EOA status, control, personhood, or permanence.
- Exact `0xef0100 || 20-byte target` is retained internally as `eip7702_delegated` but remains an EOA candidate in the public binary presentation.
- Any other nonempty code is `contract`.
- Safe and ERC-4337-specific collection are not performed. Deployed instances with bytecode are contracts; undeployed counterfactual addresses are an acknowledged no-code limitation.

This is an explicit, potentially RPC-intensive operation. Fixture builds and ordinary dbt runs never invoke it.

## HyperIndex Mode

### Live wallet scan jobs

The local API can start an additive wallet scan from the dashboard in live mode. Configure the explicit multi-wallet worker adapter before using it:

```sh
export WALLET_SCAN_COMMAND='your-multi-wallet-indexer-command'
```

The command receives `WALLET_SCAN_ADDRESS`, `WALLET_SCAN_LABEL`, the wallet's missing `WALLET_SCAN_FROM_BLOCK`, `WALLET_SCAN_TO_BLOCK`, and `WALLET_SCAN_OUTPUT_PATH`, plus (for ENS or direct-address resolution) the finalized observation source/block/hash/timestamp variables. The manager has already copied the complete live artifact to the output path; the worker updates that one path in place. The worker must persist the selected run's finalized/provenance fields, preserve all existing wallet/run rows and shared enrichment/cache rows, and exit successfully. Only one job runs at a time. The manager validates and atomically replaces `analytics/artifacts/live.duckdb` after success; a failure never replaces or serves a partial artifact. The command remains an explicit adapter boundary: it owns chain collection and wallet merge behavior, while the manager owns atomic publication and preservation validation.

Run the indexer locally:

```sh
bun run indexer:dev
```

The low-level bounded indexer entrypoint is reserved for the scan worker and assumes the local
Envio Postgres/Hasura environment is already running:

```sh
bun run indexer:scan -- \
  --wallet 0x0000000000000000000000000000000000000001 \
  --from-block 100 --to-block 200 \
  --schema wallet_scan_example --indexer-port 8082
```

It creates an ignored temporary Envio config, applies the inclusive `start_block`/`end_block`, and
runs `envio start --restart` only inside the required `wallet_scan_*` Postgres schema. The schema
and non-default port isolate the bounded process from the persistent `public` indexer. Never pass a
persistent schema to this command. This entrypoint checks only address, range, schema, and port
syntax; it does not resolve Ethereum finality or verify an end-block hash. The higher-level scan
worker must supply the already-pinned finalized range, merge and checkpoint the resulting rows,
and clean up the temporary schema. Running `indexer:scan` directly does not update the shared raw
dataset or `live.duckdb`.

Local HyperIndex requires Docker and an `ENVIO_API_TOKEN`. The indexer uses Envio wildcard indexing with topic filters for the configured wallet and writes `Erc20Transfer` entities to Postgres. It persists the canonical block hash provided with each event, while its opt-in field selection includes top-level transaction `from` and `to`; the transaction-envelope columns are nullable so existing rows can remain readable during migration. Raw event duplication is disabled.

Run `bun run indexer:codegen` after changing the Envio field selection or entity schema. Adding the nullable transaction-envelope columns did not retroactively populate already-processed entities, and the newer non-null block-hash entity field requires rebuilding the historical entities. Before the next live DuckDB build on this contract, use Envio's restart/reindex operation for the intended range; do not point `stg_transfer_events` at an older `Erc20Transfer` table that lacks `block_hash`. Until replay, the existing artifact preserves missing senders/targets as null, relation evidence as `unknown`, and `is_indirect` as null. A normal fixture build, export, or dashboard run never starts that backfill.

After the indexer has created and populated `public."Erc20Transfer"`, export its Postgres connection URI and build in live mode:

```sh
export DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN='postgresql://USER:PASSWORD@127.0.0.1:PORT/DATABASE'
bun run analytics:build:hyperindex
```

dbt-duckdb attaches that database read-only as the `hyperindex` catalog. The wrapper stops with a clear error when live mode is requested without the DSN. Confirm the mapped local port with `docker port envio-postgres 5432`; this project currently maps it to `5433`. Store the URI under `analytics.hyperindex_postgres_dsn` in ignored `config.yaml` to avoid exporting it in every shell.

The first successful build records one wallet-scoped `ops.pipeline_runs` row from HyperIndex `_meta.startBlock` through the chosen finalized block for the selected wallet. Live wallet selection uses the durable `ops.wallet_targets` registry; `wallets.csv` remains fixture-only. Set `EVM_WALLET_SCAN_ADDRESS` when more than one live target exists; the value is normalized before selection, and an unset selector with multiple targets fails clearly. Each later snapshot for the selected wallet begins at that wallet's previous completed `to_block + 1`; failed rows do not advance coverage and the same interval remains retryable. The ingestion adapter must first call the raw-ingestion checkpoint with its observed event count. If publication then fails, the next attempt reuses that failed run and its already-ingested interval instead of re-indexing raw data. A run records its finalized end-block hash and completes only after dbt succeeds. A worker scan publishes the selected wallet's updated projection into the complete live artifact without deleting other wallet projections or shared enrichment/cache rows. Adding wallet B therefore creates no new run for wallet A, but wallet A's analytics and coverage metadata remain available alongside B. `HYPERINDEX_GRAPHQL_URL` or `analytics.hyperindex_graphql_url` may override the local GraphQL default.

An ordinary dbt failure marks its run `failed`. An abrupt process termination can leave a `running` row; the next build refuses to overlap it. Inspect that row before manually marking it failed, then rerun the same command. Do not delete a completed row to move the checkpoint: completed ranges are the evidence for cumulative continuity. `ingestion_status` and `raw_ingested_at` describe durable raw persistence, not a successful analytics publication; `status=completed` is reserved for the latter.

The resulting `analytics/artifacts/live.duckdb` is the local application's query source and contains all completed wallet projections, orchestration-owned `ops.pipeline_runs`, shared enrichment inputs, and the isolated application-owned recognition override table. Token and account enrichment candidate selection also reads this live artifact exclusively and skips addresses already present in their global caches. Do not export full live history through the fixture-demo exporter. Start the local API with the same `EVM_WALLET_SCAN_ADDRESS` used for the build when selecting a wallet; if it is omitted, the API derives the active wallet only when the artifact has exactly one metadata wallet and fails clearly otherwise. The API verifies that metadata references the latest completed finalized run independently for every wallet, that completed intervals are contiguous, and that their cumulative `events_found` reconciles with each wallet's `pipeline_metadata.transfer_count`. It then opens one short-lived DuckDB connection per request, applies overrides and filters before exact aggregation/ranking, and paginates event rows with a stable opaque cursor.

## Fixture Demo Export

```sh
bun run export:dashboard
```

Run this only after the fixture build. It creates:

- `public/data/summaries.json`
- `public/data/timeline.json`
- `public/data/events.json`
- `public/data/meta.json`

These files are the static GitHub Pages demonstration contract. `meta.json` advertises `dashboard-export-v1`, includes observed fixture block/time extrema, keeps cumulative scan coverage explicitly unrecorded, and calculates each complete/exported count and sampling flag from the exact DuckDB relation delivered. The files must remain bounded, identify fixture provenance, and never claim to be complete HyperIndex history. Files are replaced atomically so readers never observe a partially written individual JSON file.

The exporter bounds its fixture rows across the nine non-empty recognition/address-evidence selections the static dashboard supports. The live dashboard computes only the requested selection through DuckDB-backed API endpoints.

`bun run dashboard:build` always produces the fixture/static build used by CI and Pages. To inspect that exact adapter locally, run `bun run dashboard:dev:fixture`. Do not use the fixture command to validate the live API path.

## Verification

```sh
bun run static:check
bun run test
```

The static gate runs Oxlint and Ruff before generating the local Envio handler types,
checking TypeScript with `tsc`, and checking Python with Pyright. Install
`requirements-dev.txt` in addition to `bun install` before running it locally. These
tools are pinned and configured for high-signal checks so the gate stays fast and
avoids repository-wide style churn.

The full test command builds `analytics/artifacts/fixture.duckdb`, exports fixture JSON, runs JS tests, and runs dbt tests against that fixture artifact. It can overwrite ignored fixture JSON under `public/data`, but it does not modify `analytics/artifacts/live.duckdb` or attach HyperIndex.

## GitHub CI and Deployment

`.github/workflows/ci.yml` runs the fast mandatory static gate, reproducible fixture-demo pipeline, and production static build for pull requests and pushes to `main`. It also runs advisory JavaScript and Python dependency audits. The uploaded production build is retained for one day to help diagnose a run; this retention setting does not control how long a deployed site stays online.

`.github/workflows/deploy.yml` rebuilds the fixture-backed static demo from the exact revision that passed `main` CI and publishes it to GitHub Pages. It does not deploy the complete local database-backed application. Deployment is disabled by default. To enable it when the repository and GitHub plan support Pages:

1. Set the repository Actions variable `ENABLE_GITHUB_PAGES` to `true`.
2. In repository Pages settings, select GitHub Actions as the source if GitHub does not configure it automatically.
3. Run the Deploy workflow manually once, or merge a change into `main` and let successful CI trigger it.

The demo site does not expire after one day; only the separate CI download artifact does. If private-repository Pages is unavailable on the current plan, keep the gate disabled and connect the fixture-demo build to a static host that supports private Git integration, such as Cloudflare Pages, Netlify, or Vercel. Set the host's build command to `bun run test && bun run dashboard:build` and its output directory to `dist`.

The planned local distribution is separate from static deployment. It will use Docker to package the indexer, persistence, transformation/API workflow, and frontend with explicit persistent volumes, secrets, health checks, and startup order. No Docker or Compose contract exists in the repository yet.

Dependabot checks Actions, JavaScript, indexer, and Python dependencies weekly. Pull requests inherit the repository template and Copilot review instructions, but branch protection and automatic Copilot review assignment are repository settings and must be enabled separately when desired.

## Local Codex Review

Run `bun run hooks:install` once per clone to set this repository's `core.hooksPath` to `.githooks`. The pre-commit hook delegates to `scripts/codex_review_gate.sh`, which starts a new ephemeral Codex process with a read-only sandbox and no approval prompts. The reviewer is instructed to inspect only the staged diff and emits JSON matching `.codex/review-output.schema.json`; the wrapper validates that response before allowing the commit. Material drift between changed behavior or architecture and its owning documentation is a blocking correctness finding, while behavior-preserving implementation details do not require mechanical documentation edits.

This is an advisory AI review promoted to a local gate, not a proof of correctness. It adds network latency and consumes Codex usage, so the deterministic test suite and remote CI remain required. The hook fails closed when Codex, Bun, authentication, or connectivity is unavailable. Use `SKIP_CODEX_REVIEW=1` only as an explicit one-commit escape hatch; the bypass is visible in the terminal but is not recorded in Git history.
