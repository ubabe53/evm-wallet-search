# Operations

## Local Setup

```sh
bun install
bun run indexer:dev
bun run analytics:build:hyperindex
```

This is the primary local-product data path. `analytics:build:hyperindex` bootstraps Python dbt dependencies from `analytics/requirements.txt` if dbt is not installed in the active Python environment, reads the already indexed HyperIndex entity table, and builds the DuckDB marts in `analytics/artifacts/live.duckdb`.

Start the read-only API after the live build:

```sh
bun run api:dev
```

The service binds only to `127.0.0.1:8000`, refuses fixture provenance, and exposes readiness at `/api/v1/health` plus interactive OpenAPI documentation at `/docs`. Stop the API before rebuilding `live.duckdb`; DuckDB permits multiple read-only processes, but the dbt writer and API reader must not access the same file concurrently. Restart the API and reload the dashboard after a successful live build so every request and the browser's snapshot metadata use the new artifact.

In a second terminal, run `bun run dashboard:dev`. Vite selects the live API adapter and proxies `/api` to `127.0.0.1:8000`; it does not load `public/data`. Fixture and live dbt artifacts are isolated, so deterministic validation cannot replace the live database.

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
    batch_size: 100
    max_retries: 2
    fallback_confirmations: 64
```

## Fixture Demo Mode

Fixture mode exists for deterministic tests and the eventual GitHub Pages portfolio demo. It is not the primary local application mode and does not stand in for HyperIndex verification.

```sh
bun run analytics:build:fixture
```

The six fixture transfer rows live in `analytics/seeds/raw_erc20_transfers_fixture.csv`. They cover direct, indirect, and legacy-unknown transaction-envelope evidence while preserving emitted Transfer fields. There is no account-evidence fixture: the fixture build uses an empty typed relation, so it never invents address classifications. Wallet and token seeds live in `analytics/seeds/wallets.csv` and `analytics/seeds/token_metadata.csv`. Fixture builds write `analytics/artifacts/fixture.duckdb`, remove any live Postgres DSN from the dbt child process, and never attach HyperIndex. Exported `meta.json` records `data_source: fixture`, and the demo displays a fixture badge.

`bun run analytics:build` remains an alias for `analytics:build:fixture` so existing CI and contributor commands stay deterministic. The exporter reads only the fixture database and may overwrite only the ignored files under `public/data/`.

## Token Registry

Ordinary analytics builds use the checked-in registry without internet access. Refresh it explicitly with:

```sh
bun run labels:sync
```

The command validates Ethereum addresses and decimals, fails on cross-source decimal conflicts, and rewrites `analytics/seeds/token_metadata.csv` plus `token_metadata_manifest.json`. Naming precedence is Trust Wallet, Uniswap, then CoinGecko; manual entries in `token_label_overrides.csv` override every generated source.

Each reviewed manual `trusted` approval or `spam` entry must include a reason and evidence URL. Suspected spam is automated rather than manually assigned. Unknown tokens should be left unlisted and will receive `unknown` quality plus `unverified` status automatically; CoinGecko absence never implies spam. After a seed schema change, run one migration build with `python3 scripts/run_dbt.py build --full-refresh`; routine registry content refreshes use the normal build command.

## Spam Classification

Classification runs during every dbt build and makes no network calls. Inspect contract-level evidence in `int_token_reputation`, wallet-token behavior in `int_wallet_token_interactions`, and the effective event status in `wallet_events`. Scores, reason codes, provenance, and classifier versions remain available internally in DuckDB and the typed transitional payload; the dashboard does not expose that evidence.

The dashboard has one `Include spam` toggle, off by default. Off excludes both automated `suspected_spam` and reviewed `spam`; on includes both under one user-facing `Spam` label. It does not show a trusted label or a quality filter. To change a threshold or reason rule, update the corresponding model, its version string, dbt tests, and `docs/architecture.md` in the same change.

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

Collect pinned code evidence for every unresolved event counterparty:

```sh
bun run addresses:enrich
```

The command selects distinct `wallet_events.counterparty_address` values, excluding the configured wallet and zero address. It verifies Ethereum mainnet, resolves one concrete `safe` block, and passes that block number to every `eth_getCode`. If the provider does not support the `safe` tag, it pins `latest` minus the configured confirmation buffer. Block number, hash, timestamp, finality policy, and fetch time are stored with every result.

The ignored `analytics/artifacts/account_evidence.duckdb` cache is checkpointed after every JSON-RPC batch. Successful rows are never selected or overwritten automatically; failed or malformed results stay `unknown` and are retried by a later invocation. The default run has no address limit. `--limit` exists only for an intentional partial run.

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
```

dbt-duckdb attaches that database read-only as the `hyperindex` catalog. The wrapper stops with a clear error when live mode is requested without the DSN. Confirm the mapped local port with `docker port envio-postgres 5432`; this project currently maps it to `5433`. Store the URI under `analytics.hyperindex_postgres_dsn` in ignored `config.yaml` to avoid exporting it in every shell.

The resulting `analytics/artifacts/live.duckdb` is the local application's query source. Token and account enrichment candidate selection also reads this live artifact exclusively. Do not export full live history through the fixture-demo exporter. The API opens one read-only DuckDB connection per request, applies filters before exact aggregation/ranking, and paginates event rows with a stable opaque cursor.

## Fixture Demo Export

```sh
bun run export:dashboard
```

Run this only after the fixture build. It creates:

- `public/data/graph.json`
- `public/data/summaries.json`
- `public/data/timeline.json`
- `public/data/events.json`
- `public/data/meta.json`

These files are the static GitHub Pages demonstration contract. They must remain bounded, identify fixture provenance, and never claim to be complete HyperIndex history. Files are replaced atomically so readers never observe a partially written individual JSON file.

The exporter still contains legacy candidate-union logic across 6,615 composed filter selections. Do not use that behavior for live local data or expand it; the live dashboard now computes only the requested selection through DuckDB-backed API endpoints.

`bun run dashboard:build` always produces the fixture/static build used by CI and Pages. To inspect that exact adapter locally, run `bun run dashboard:dev:fixture`. Do not use the fixture command to validate the live API path.

## Verification

```sh
bun run test
```

The full test command builds `analytics/artifacts/fixture.duckdb`, exports fixture JSON, runs JS tests, and runs dbt tests against that fixture artifact. It can overwrite ignored fixture JSON under `public/data`, but it does not modify `analytics/artifacts/live.duckdb` or attach HyperIndex.

## GitHub CI and Deployment

`.github/workflows/ci.yml` runs the reproducible fixture-demo pipeline and production static build for pull requests and pushes to `main`. It also runs advisory JavaScript and Python dependency audits. The uploaded production build is retained for one day to help diagnose a run; this retention setting does not control how long a deployed site stays online.

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
