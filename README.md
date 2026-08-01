# EVM Wallet Search

An evidence-first Ethereum wallet interaction dashboard for one selected configured wallet. The project
indexes wallet-relevant `Transfer(address,address,uint256)` logs with Envio HyperIndex, builds
reproducible DuckDB analytics with dbt, and serves them through a loopback FastAPI API to a React
dashboard.

The current target is Ethereum mainnet (`chain_id = 1`) and the pinned address
`0xd8da6bf26964af9d7eed9e03e53415d37aa96045`. Its `vitalik.eth` label is project configuration,
not a live ENS-resolution claim unless a scan job explicitly resolves it through the server-side
ENS input boundary at a finalized block.

> [!IMPORTANT]
> The event source is ERC-20-intended, not standards-proof. ERC-721 uses the same `Transfer`
> signature, and the wildcard indexer does not yet disambiguate token standards. A captured log
> proves that a contract emitted the signature; it does not prove intent, economic ownership,
> transaction initiation, standards compliance, token legitimacy, or historical account type.

## MVP boundary

The MVP includes emitted Transfer participants and exact raw values, wallet-relative direction,
selected top-level transaction sender/target evidence, exact-address token recognition, and
pinned-block bytecode observations for counterparties.

It does not include native ETH transfers, traces, internal calls, approvals, NFT-specific
interpretation, arbitrary wallet lookup, USD prices, or an implemented Docker distribution.
Recognition means registry membership or a manual local override—not safety. `EOA` presentation
means no bytecode was observed at one pinned block—not proof of personhood, control, permanence,
or account history.

## Architecture

```mermaid
flowchart LR
    eth["Ethereum mainnet<br/>Transfer-signature logs"] --> indexer["Envio HyperIndex<br/>indexer/"]
    indexer --> postgres["HyperIndex Postgres<br/>ingestion persistence"]
    postgres --> dbt["dbt transformations<br/>analytics/"]
    enrich["Offline token inputs +<br/>local account evidence"] --> dbt
    dbt --> live["live.duckdb<br/>finalized-range snapshot"]
    live --> api["Loopback FastAPI<br/>server/"]
    api --> dashboard["React dashboard<br/>src/"]

    fixtures["Checked-in fixtures"] --> fixturedb["fixture.duckdb"]
    fixturedb --> export["Bounded JSON exporter"]
    export --> static["Static fixture demo"]
```

The two delivery paths are deliberately separate. Local development queries complete matching
rows within the recorded `live.duckdb` coverage through the API. The static build reads only
bounded fixture JSON and cannot establish live HyperIndex coverage. See
[ARCHITECTURE.md](ARCHITECTURE.md) for dependency rules, trust boundaries, and known gaps.

The wallet seed may contain more than one target, but each live build selects exactly one with
`EVM_WALLET_SCAN_ADDRESS`; when it is unset, exactly one configured wallet is required. The live
artifact is a single-wallet projection. It does not merge separate wallet builds or claim combined
persistence; a later dashboard merge worker requires an explicit architecture and data-contract
decision.

## Dashboard and demo

The local dashboard exposes:

- exact selection totals alongside bounded rankings and cursor-paginated events;
- yearly/monthly captured-event timelines with explicit inbound, outbound, and self directions;
- token and counterparty rankings by captured event count, never cross-token quantity or value;
- provenance that separates finalized scan coverage from observed event extrema;
- `All`, `Recognized`, and `Other` token views plus pinned-block `EOA`/`Contract` evidence.

The production Vite build is the deterministic fixture demo. It is useful for interaction and
presentation checks, but its fixture badge, bounded payload, and unrecorded scan coverage are part
of the contract—not caveats to hide.

No checked-in screenshot currently matches the dashboard contract closely enough to embed here.
[`docs/images/README.md`](docs/images/README.md) defines the verified slot and refresh procedure
for the next current overview image without leaving a broken link in this README.

## Quick start

Requirements: [Bun](https://bun.sh/) and Python 3. Install the reviewed Python dependency ranges
explicitly; the dbt wrapper's limited bootstrap is only a fallback when dbt is absent.

```sh
bun install
python3 -m pip install -r requirements-dev.txt
bun run analytics:build:fixture
bun run export:dashboard
bun run dashboard:dev:fixture
```

Open the local URL printed by Vite. This runs only the deterministic fixture path; it does not
start HyperIndex or produce live-wallet analytics.

For the primary local product, Docker, an Envio token, and the HyperIndex Postgres DSN are also
required; Ethereum RPC can use the configured public fallback. Follow the
[live setup and recovery guide](docs/operations.md#local-setup) rather than treating the fixture
quick start as a production workflow. Set `EVM_WALLET_SCAN_ADDRESS` for both the live build and
the local API process when selecting a wallet. The live API has no hardcoded wallet fallback: if
the variable is unset, it derives the wallet from the artifact's sole current metadata row and
fails clearly if no unique wallet is available. The pinned Vitalik target belongs only to
fixture/demo configuration.

## Repository map

| Path | Ownership |
| --- | --- |
| [`indexer/`](indexer/README.md) | Envio capture scope, topic filters, entity schema, and handlers |
| [`analytics/`](analytics/README.md) | dbt staging, semantic evidence, marts, seeds, and isolated DuckDB artifacts |
| [`server/`](server/README.md) | Loopback API validation, exact bounded queries, and local recognition overrides |
| [`src/`](src/README.md) | React presentation and separate live/static data adapters |
| [`scripts/`](scripts/README.md) | Explicit orchestration, enrichment, export, and review entry points |
| [`tests/`](tests/README.md) | API, UI, export, enrichment, snapshot, and indexer contract tests |
| [`docs/`](docs/README.md) | Detailed architecture, data-model, operations, and image guidance |
| [`public/data/`](public/data/) | Ignored generated fixture JSON; never hand-edit |

## Documentation

| Read this | For |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | System map, dependency direction, invariants, and current gaps |
| [docs/architecture.md](docs/architecture.md) | Detailed product behavior, semantics, filtering, and export policy |
| [docs/data-model.md](docs/data-model.md) | Grains, keys, fields, classifications, API/export contracts, and tests |
| [docs/operations.md](docs/operations.md) | Setup, credentials, commands, enrichment, recovery, and delivery |
| [AGENTS.md](AGENTS.md) | Maintainer workflow, validation, and documentation change routing |
| [dbt source contracts](analytics/models/) | Model-level descriptions, tests, provenance, consumers, and exposures |

Run `bun run static:check` for mandatory static analysis and `bun run test` for the deterministic
cross-layer suite. Fixture validation proves the fixture/demo contract; it does not prove live
HyperIndex behavior.
