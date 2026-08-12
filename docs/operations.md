# Operations

## Packaged live setup

Requirements are Bun and Docker Desktop. Copy `.env.example` to the ignored `.env` and set
`ENVIO_API_TOKEN`. `ETHEREUM_RPC_URL` is optional for ordinary scans: Compose injects the configured
public mainnet fallback when it is empty. The internal Postgres user, password, database, and both
read/write DSNs are private Compose configuration and do not need user setup.

Start the live product with one explicit initial address or ENS name:

```sh
cp .env.example .env
bun run app:up -- 0x0000000000000000000000000000000000000001
```

The launcher validates configuration, builds the application and dashboard images, starts private
Postgres plus the API/worker and web services, waits for process liveness, submits the initial scan
through `POST /api/v1/scan-jobs`, and reports the same named stages as the dashboard. It prints the
URL only after the worker has indexed the missing range through its pinned finalized endpoint,
merged durable raw rows/checkpoints, built and validated staged analytics, and published
`live.duckdb` atomically. A first wallet begins at block 0; an existing wallet resumes at its first
missing block and reuses completed raw checkpoints after a failed publication. The resolved
canonical initial target is saved without secrets under ignored `.runtime/docker.env` so it remains
the unambiguous default when several wallets exist.

Only nginx is published, on `127.0.0.1:5173` by default. Set `EVM_WALLET_APP_PORT` in `.env` if that
port is occupied. FastAPI listens on all interfaces only within the private Compose network so nginx
can reach it; Postgres and the API port are never published to the host. `/api/v1/health/live` is container
liveness and can succeed before analytics exist; `/api/v1/health` becomes ready only after valid
live provenance is available.

```sh
bun run app:status
bun run app:logs
bun run app:down
```

`app:down` removes containers and the private network but preserves the `postgres-data` and
`analytics-data` named volumes. This retains raw checkpoints, every completed wallet projection,
recognition overrides, and account-evidence cache. To diagnose a failed first scan, inspect
`bun run app:logs`, correct `.env`, and rerun the same `app:up` command; publication failures retain
the last good DuckDB artifact and durable raw checkpoints. Removing Compose volumes permanently
deletes local ingestion and analytics state and is intentionally not wrapped in a convenience
command.

The Docker path never builds or serves fixture JSON. The deterministic fixture build remains the
separate GitHub Pages demo workflow.

## Native component development

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
never passed to the indexer. This provenance is persisted in the staged complete artifact by the
bounded worker; it does not create a third analytics database or a database per wallet.

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
  wallet_scan_postgres_dsn: ""
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

Fixture mode exists for deterministic tests and the fixture-backed GitHub Pages portfolio demo. It is not the primary local application mode and does not stand in for HyperIndex verification.

```sh
bun run analytics:build:fixture
```

The compact fixture transfer set lives in `analytics/seeds/raw_transfer_events_fixture.csv`. Its dates, block identifiers, and participant pairs are synthetic examples—not historical `vitalik.eth` activity—and span five UTC years so the demo can exercise year/month navigation, a bounded 10-row event view, direct and confirmed-indirect direction evidence, self-transfer handling, multiple tokens and counterparties, and both recognition filters. There is no account-evidence fixture: the fixture build uses an empty typed relation, so it never invents address classifications. Wallet and token seeds live in `analytics/seeds/wallets.csv` and `analytics/seeds/token_metadata.csv`. Fixture builds write `analytics/artifacts/fixture.duckdb`, remove any live Postgres DSN from the dbt child process, and never attach HyperIndex. Exported `meta.json` records `data_source: fixture`, and the demo displays its synthetic provenance, unrecorded coverage, exported/complete fixture counts, sampling state, and configured-label caveat.

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

For the packaged stack, set an explicit `ETHEREUM_RPC_URL` in `.env` and run:

```sh
bun run app:enrich
```

This explicit maintenance command stops FastAPI, collects only unresolved counterparty evidence
into the persistent shared cache, and rebuilds every completed wallet from its recorded cumulative
finalized interval in a temporary copy of `live.duckdb`. It verifies that immutable event facts,
finalized coverage, run/generation history, wallet targets, and recognition overrides are unchanged
before atomic publication, then restarts FastAPI even if collection or rebuilding fails. A failed
publication leaves the previously served artifact intact; successfully checkpointed evidence stays
in the separate cache and is reused on retry. The command refuses the public fallback because a
fresh wallet can require many `eth_getCode` calls.

This maintenance path does not use HyperSync and therefore does not require `ENVIO_API_TOKEN` once
the live stack and persistent data already exist. Starting or advancing a wallet scan still requires
the Envio token and `app:up` continues to fail fast when it is absent.

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

The local API starts the bundled additive wallet worker by default. Configure the ordinary
read-only dbt source URI for manual live builds and an explicit write-capable worker URI:

```sh
export DBT_ENV_SECRET_HYPERINDEX_POSTGRES_DSN='postgresql://READER:PASSWORD@127.0.0.1:5433/envio-dev'
export WALLET_SCAN_POSTGRES_DSN='postgresql://WRITER:PASSWORD@127.0.0.1:5433/envio-dev'
```

For a scan job, the worker uses `WALLET_SCAN_POSTGRES_DSN` for the raw transaction and passes that
exact URI to dbt's read-only attachment, so persistence and transformation cannot accidentally
target different databases. The manager supplies job identity/original input, canonical wallet/label, the wallet's first missing
through finalized range, output path, and resolver observation provenance. The bundled worker starts
one isolated bounded Envio schema, proves Envio reached the requested end, rechecks the endpoint
against current finalized RPC evidence, transactionally merges raw rows and a durable checkpoint,
drops the temporary schema, and runs dbt against the staged artifact. Only one job runs at a time.
The manager then validates provenance and preservation before atomically replacing
`analytics/artifacts/live.duckdb`; it protects canonical event identities, immutable event facts,
shared RPC observations, run history, and application overrides without requiring recomputed dbt
summary rows to remain byte-for-byte unchanged. Failures never publish a partial artifact. Set
`WALLET_SCAN_COMMAND` only to override this first-party subprocess contract deliberately.

Envio remains a service after reaching a configured `end_block`, so the worker supervises it
explicitly: it polls the isolated `envio_chains` checkpoint, terminates and reaps the process group
after readiness, and fails on early process exit or timeout. The default timeout is 7200 seconds;
set `WALLET_SCAN_INDEXER_TIMEOUT_SECONDS` between 1 and 86400 when a deliberate large backfill needs
a different bound. A timeout never creates a completed raw checkpoint or publishes DuckDB state.

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

The first successful build records one wallet-scoped `ops.pipeline_runs` row from its configured start through the chosen finalized block. Live wallet selection uses the durable `ops.wallet_targets` registry; `wallets.csv` remains fixture-only. Set `EVM_WALLET_SCAN_ADDRESS` when more than one live target exists; the value is normalized before selection, and an unset selector with multiple targets fails clearly. Each later snapshot for the selected wallet begins at that wallet's previous completed `to_block + 1`; failed rows do not advance coverage and the same interval remains retryable. A bounded worker run writes immutable raw rows once to shared `wallet_scan.transfer_events` and its completed interval to `wallet_scan.ingestion_runs`. This shared relation is sufficient for a fresh Compose database; a normal `public."Erc20Transfer"` relation is included when an independent main indexer has created it, but is not fabricated as an empty prerequisite. If dbt, staged validation, or atomic publication fails afterward, the next dashboard attempt reuses contiguous completed raw checkpoints from that still-missing start. It skips an exactly completed interval or, when the newly pinned finalized endpoint advanced, indexes only the uncheckpointed tail before creating a fresh DuckDB run and retrying transformation/publication. `HYPERINDEX_GRAPHQL_URL` or `analytics.hyperindex_graphql_url` may override the local GraphQL default.

An ordinary manual dbt failure marks its run `failed`. An abrupt process termination can leave a `running` row in its target artifact; inspect that row before manually changing it. Dashboard jobs write run state only to their temporary artifact until publication, so a failed staging directory is discarded; the separate Postgres ingestion checkpoint is what makes their raw retry idempotent. Do not delete a completed row to move coverage. `ingestion_status` and `raw_ingested_at` describe durable raw persistence, not a successful analytics publication; `status=completed` is reserved for the latter.

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

`.github/workflows/ci.yml` runs the fast mandatory static gate, reproducible fixture-demo pipeline, and production static build for pull requests and pushes to `main`. A separate package job validates `compose.yaml` and builds both live distribution images without starting Postgres, contacting Ethereum, running an index, or requiring credentials. CI also runs advisory JavaScript and Python dependency audits. The uploaded production build is retained for one day to help diagnose a run; this retention setting does not control how long a deployed site stays online.

`.github/workflows/deploy.yml` rebuilds the fixture-backed static demo from the exact revision that passed `main` CI and publishes it to GitHub Pages. It does not deploy the complete local database-backed application. Deployment is disabled by default. To enable it when the repository and GitHub plan support Pages:

1. Set the repository Actions variable `ENABLE_GITHUB_PAGES` to `true`.
2. In repository Pages settings, select GitHub Actions as the source if GitHub does not configure it automatically.
3. Run the Deploy workflow manually once, or merge a change into `main` and let successful CI trigger it.
4. Verify the published repository subpath, including `data/meta.json`, hashed assets, and `favicon.svg`; the workflow builds with `/${repository-name}/` as the Vite base.
5. Set the repository homepage URL to the verified Pages URL.
6. Capture a current screenshot only from that verified fixture deployment, following `docs/images/README.md`; do not substitute or fabricate an image.

The demo site does not expire after one day; only the separate CI download artifact does. If private-repository Pages is unavailable on the current plan, keep the gate disabled and connect the fixture-demo build to a static host that supports private Git integration, such as Cloudflare Pages, Netlify, or Vercel. Set the host's build command to `bun run test && bun run dashboard:build` and its output directory to `dist`.

The Compose live distribution and static deployment are deliberately separate. Compose packages
the complete local database-backed application; GitHub Pages publishes only bounded fixture JSON.

Dependabot checks Actions, JavaScript, indexer, and Python dependencies weekly. Pull requests inherit the repository template and Copilot review instructions, but branch protection and automatic Copilot review assignment are repository settings and must be enabled separately when desired.

## Local Codex Review

Run `bun run hooks:install` once per clone to set this repository's `core.hooksPath` to `.githooks`. The pre-commit hook delegates to `scripts/codex_review_gate.sh`, which starts a new ephemeral Codex process with a read-only sandbox and no approval prompts. The reviewer is instructed to inspect only the staged diff and emits JSON matching `.codex/review-output.schema.json`; the wrapper validates that response before allowing the commit. Material drift between changed behavior or architecture and its owning documentation is a blocking correctness finding, while behavior-preserving implementation details do not require mechanical documentation edits.

This is an advisory AI review promoted to a local gate, not a proof of correctness. It adds network latency and consumes Codex usage, so the deterministic test suite and remote CI remain required. The hook fails closed when Codex, Bun, authentication, or connectivity is unavailable. Use `SKIP_CODEX_REVIEW=1` only as an explicit one-commit escape hatch; the bypass is visible in the terminal but is not recorded in Git history.
