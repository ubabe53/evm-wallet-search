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
```

## Fixture Mode

Fixture mode is the default so the project can be built and tested without a live HyperIndex Postgres database.

```sh
bun run analytics:build
```

The five fixture transfer rows live in `analytics/seeds/raw_erc20_transfers_fixture.csv`. Wallet and token seeds live in `analytics/seeds/wallets.csv` and `analytics/seeds/token_metadata.csv`. Exported `meta.json` records `data_source: fixture`, and the dashboard displays a fixture badge.

## Token Registry

Ordinary analytics builds use the checked-in registry without internet access. Refresh it explicitly with:

```sh
bun run labels:sync
```

The command validates Ethereum addresses and decimals, fails on cross-source decimal conflicts, and rewrites `analytics/seeds/token_metadata.csv` plus `token_metadata_manifest.json`. Naming precedence is Trust Wallet, Uniswap, then CoinGecko; manual entries in `token_label_overrides.csv` override every generated source.

Each manual `suspected_spam` or `spam` entry must include a reason and evidence URL. Unknown tokens should be left unlisted and will receive `unverified` automatically; CoinGecko absence never implies spam. After a seed schema change, run one migration build with `python3 scripts/run_dbt.py build --full-refresh`; routine registry content refreshes use the normal build command.

## Spam Classification

Classification runs during every dbt build and makes no network calls. Inspect contract-level evidence in `int_token_reputation`, wallet-token behavior in `int_wallet_token_interactions`, and the effective event status in `wallet_events`. Scores, reason codes, and classifier versions are exported to the dashboard; hovering a suspected badge displays the evidence.

The Include spam control hides or reveals both `suspected_spam` and reviewed `spam`. The Status menu can then select either independently. To change a threshold or reason rule, update the corresponding intermediate model, its version string, dbt tests, and `docs/architecture.md` in the same change.

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

## Counterparty Type Enrichment

Classify the next 500 high-activity counterparties by bytecode at one pinned Ethereum block:

```sh
bun run addresses:enrich --limit 500
```

The command ranks distinct counterparties by complete wallet transfer count, checks Ethereum mainnet, batches `eth_getCode`, and writes `analytics/seeds/counterparty_code_metadata.csv`. Non-empty bytecode is `contract`, empty bytecode is `wallet`, and failed or malformed results are `unknown`. It uses the same `ETHEREUM_RPC_URL` / `config.yaml` / public-fallback precedence as token enrichment.

```sh
bun run addresses:enrich --limit 500 --retry-failed
bun run addresses:enrich --limit 500 --refresh
```

Normal mode advances to unattempted addresses, retry mode retries failed checks, and refresh mode rechecks ranked addresses at a new pinned block. Run the live analytics build and dashboard export after enrichment. A `wallet` result means only that the address had no bytecode at the snapshot block; it is not proof of an EOA or human-controlled account.

## HyperIndex Mode

Run the indexer locally:

```sh
bun run indexer:dev
```

Local HyperIndex requires Docker and an `ENVIO_API_TOKEN`. The indexer uses Envio wildcard indexing with topic filters for the configured wallet and writes `Erc20Transfer` entities to Postgres. Raw event duplication is disabled.

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

The JSON is bounded for static-browser performance: up to 1,000 newest events, 250 top graph interactions, and 500 token-summary rows per token status; 500 counterparties and 5,000 timeline rows overall. Files are replaced atomically so readers never observe partially written JSON. The complete transformed data remains in `analytics/wallet_analytics.duckdb`. Inspect `meta.json` for full status-combination counts, complete and exported row counts, limits, and `is_sampled` before publishing or debugging a dashboard snapshot.

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
