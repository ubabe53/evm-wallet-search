# Three-Agent Feature Integration Report

Date: 2026-07-19  
Repository: `ubabe53/evm-wallet-search`  
Integrated branch: `main`  
Integrated revision: `30a942d3819db92c897bdb9f2f5658d514578799`

## 1. Executive summary

Three independent Codex CLI sessions implemented three related improvements in isolated Git worktrees:

1. Transaction-initiation evidence and indirect ERC-20 transfer labeling.
2. Evidence-based account classification, including Safe, ERC-4337, and EIP-7702 evidence.
3. Token-quality tiers separated from metadata availability and spam reputation.

Each agent worked on its own branch, used the repository's pre-commit review gate, pushed its branch, opened a pull request, and waited for GitHub CI. The pull requests were then integrated in this order:

1. [PR #14 — transaction initiation](https://github.com/ubabe53/evm-wallet-search/pull/14)
2. [PR #16 — account evidence](https://github.com/ubabe53/evm-wallet-search/pull/16)
3. [PR #15 — token quality](https://github.com/ubabe53/evm-wallet-search/pull/15)

All three GitHub `Verify application` checks passed before merge. The advisory dependency-audit checks also passed.

The final integrated change from the pre-feature base `b270ce8` to `30a942d` touched 54 files, with approximately 4,814 insertions and 1,373 deletions. The largest areas of work were the dbt contracts and tests, account-enrichment logic, bounded dashboard exporter, React dashboard, TypeScript data contract, and test suite.

## 2. How the work was orchestrated

### 2.1 Worktree layout

The main checkout and feature worktrees are:

| Purpose | Branch | Path | Final feature commit |
|---|---|---|---|
| Integration | `main` | `/Users/ubabe/Documents/evm-wallet-search` | `30a942d` |
| Transaction initiation | `agent/transaction-initiation` | `/Users/ubabe/Documents/evm-wallet-search-worktrees/transaction-initiation` | `070b93f` |
| Account evidence | `agent/account-evidence` | `/Users/ubabe/Documents/evm-wallet-search-worktrees/account-evidence` | `a4f2886` |
| Token quality | `agent/token-quality` | `/Users/ubabe/Documents/evm-wallet-search-worktrees/token-quality` | `b52c126` |

The three feature worktrees are currently clean. They remain available for inspection or follow-up work.

### 2.2 Codex CLI sessions

Each worktree has a dedicated Codex CLI terminal still running inside Herdr. Each CLI was launched with:

- Model: `gpt-5.6-sol`
- Reasoning effort: `high`
- A worktree-specific implementation prompt
- An explicit instruction to use the `advise-web3-data` skill
- An explicit instruction to run deterministic tests, the full suite, and the dashboard build
- An explicit instruction to use the configured pre-commit review gate without bypassing it
- An explicit instruction to push and open a draft PR, but not merge it

This kept feature implementation independent while leaving merge order, semantic reconciliation, and conflict handling with the main orchestrator.

### 2.3 Ignored local files and dependencies

The worktrees were provisioned with the local runtime material needed to behave like the main checkout. At the time of this report, every worktree has:

- `config.yaml`
- `node_modules`
- `analytics/wallet_analytics.duckdb`

There is no `.env` in the main checkout, so there was no `.env` to propagate. These runtime files remain ignored and were not added to the feature commits.

### 2.4 Pre-commit behavior

The repository-wide Git configuration reports `core.hooksPath = .githooks` in the main checkout and all three worktrees. Therefore commits created from the feature worktrees used the same pre-commit system as the main checkout.

The feature PR descriptions record that the configured Codex staged-review/pre-commit gate passed without bypassing it.

## 3. Why the merge order was chosen

The branches overlapped heavily in the analytics, exporter, TypeScript, dashboard, fixtures, and tests. The order was selected by semantic dependency, not PR number.

### 3.1 PR #14 first: transaction facts and evidence

Transaction initiation introduced new event-level facts and nullable evidence fields. Those fields sit low in the pipeline and affect later classification and presentation. Integrating this first established the raw and derived transaction contract that the other features needed to preserve.

### 3.2 PR #16 second: account evidence

Account evidence changed counterparty classification throughout staging, marts, exporter, filters, and UI. It also introduced independent Safe and ERC-4337 predicates. Integrating it after transaction initiation allowed its broad UI and exporter changes to retain the newly added transaction fields.

### 3.3 PR #15 last: token quality and composed filtering

Token quality had the broadest overlap with the already-modified exporter, dashboard filters, summaries, and ranking contracts. It was merged last so its final integration commits could compose token status, token quality, and account evidence together instead of overwriting one another.

Two follow-up commits on that branch were specifically important to integration:

- `2d240d4` — `fix: compose token and account evidence`
- `b52c126` — `fix: align token ranking invariants`

This order produced one composed filter model rather than three independent filters with inconsistent totals.

## 4. Feature 1: transaction-initiation evidence

PR: [#14](https://github.com/ubabe53/evm-wallet-search/pull/14)  
Feature commit: `070b93f78d91ae715d126aa0e1b193f411e3f84f`  
Merge commit: `51feba9b9a8d786f486788db753d049f42998977`

### 4.1 Problem being solved

An ERC-20 `Transfer` log has its own `from` and `to` fields, but those fields do not necessarily identify who initiated the top-level Ethereum transaction.

Examples include:

- `transferFrom` activity
- routers and aggregators
- Safe execution
- account-abstraction flows
- token contracts that emit synthetic or unsolicited transfers

Previously, the application could show wallet-relative in/out direction, but it could not distinguish the emitted transfer participants from the transaction envelope. This made suspicious or indirect activity harder to interpret.

### 4.2 Semantic decision

The implementation deliberately keeps three concepts separate:

1. The ERC-20 event's emitted `Transfer.from` and `Transfer.to`.
2. Direction relative to the configured wallet.
3. Nullable top-level transaction sender and target evidence.

An event is marked indirect only when an observed top-level transaction sender differs from the emitted `Transfer.from`.

Important consequences:

- Missing transaction-envelope data remains unknown.
- A sender mismatch is explanatory evidence, not proof of spam.
- Existing historical rows remain valid even when the new nullable fields are absent.
- No traces, state deltas, arbitrary calls, or native ETH transfers were added.

### 4.3 Indexer changes

Envio now selects top-level transaction `from` and `to` fields and stores them as nullable entity fields alongside the existing transfer log data.

The normalized event still preserves:

- chain ID
- block number and timestamp
- transaction hash and index
- log index
- token address
- emitted transfer sender and recipient
- exact raw token value

Because existing indexed entities were created before the new fields existed, a re-index or backfill is required before historical live rows can claim complete transaction-initiation coverage.

### 4.4 Analytics changes

The transaction evidence is carried through staging, intermediate models, `wallet_events`, token summaries, and the pipeline tests.

Derived evidence includes:

- transaction sender relation to the transfer participants
- transaction target relation to the token contract or participants
- nullable `is_indirect`
- indirect inbound transfer counts
- indirect outbound transfer counts

Interaction-legitimacy scoring only awards the outbound-initiator component when every relevant broad outbound event has observed sender evidence that matches the emitted transfer sender. Unknown or mismatched evidence adds neither the score nor the reason.

### 4.5 Dashboard changes

The bounded export and TypeScript contract now preserve the raw event participants and nullable transaction-envelope evidence.

Indirect inbound/outbound activity is shown with an asterisk. Its explanation covers legitimate routing and account-abstraction cases as well as synthetic/spam possibilities, while explicitly avoiding the claim that a mismatch proves spam.

Transaction-envelope fields are also included in event search and recent-event inspection.

### 4.6 Validation reported by the agent

- `bun run indexer:codegen`
- focused indexer Vitest checks
- `bunx tsc --noEmit`
- fixture analytics build
- dbt analytics tests
- Python label/export tests
- dashboard export
- JavaScript tests
- full `bun run test`
- production dashboard build
- pre-commit Codex review gate
- GitHub `Verify application`: passed

The PR changed 27 files with 425 insertions and 30 deletions.

## 5. Feature 2: evidence-based account classification

PR: [#16](https://github.com/ubabe53/evm-wallet-search/pull/16)  
Feature commits:

- `26a8a9a` — evidence-based account classification
- `1dc6a5e` — bounded ERC-4337 evidence scans
- `a4f2886` — preserved account-evidence contracts

Merge commit: `67e40e6d4be13ee6983634574452fedbf9513af6`

### 5.1 Problem being solved

The former contract/no-contract distinction was too coarse and potentially misleading:

- a Safe is a contract but is also used as an account
- an ERC-4337 sender can be an account-like contract
- an EIP-7702 delegated EOA has code-shaped evidence without being an ordinary deployed contract
- observing no code does not prove that an address is controlled by a person

The new model replaces a simplistic identity claim with evidence observed at a pinned block.

### 5.2 Primary account types

The primary `account_type` values are:

- `eoa_candidate`
- `eip7702_delegated`
- `safe`
- `erc4337_account`
- `contract`
- `unknown`

These labels describe address evidence, not personhood, ownership, or permanent identity.

Safe and ERC-4337 evidence are retained as independent booleans. An address can therefore satisfy both filters even though only one value is used as the primary account type.

### 5.3 Evidence contract

The counterparty enrichment contract now records:

- chain ID and address
- pinned observation block and timestamp
- code state and byte size
- EIP-7702 delegation target
- Safe verification status, version, singleton, owner-address count, and threshold
- ERC-4337 observation status and UserOperation count
- first and last observed ERC-4337 blocks
- canonical EntryPoint address, version, deployment provenance, and source
- effective coverage and failed ranges
- fetch status and reason codes
- coverage scope, start block, and end block
- evidence-schema version and fetch time

The dashboard pipeline metadata also carries account-evidence observation ranges and coverage information.

### 5.4 EIP-7702 decision

EIP-7702 classification requires the exact delegation-code form:

```text
0xef0100 || 20-byte delegation target
```

Anything less exact does not become `eip7702_delegated`.

### 5.5 Safe decision

Safe classification is intentionally strict. It requires:

- a match to an official Ethereum-mainnet Safe singleton/deployment in the checked-in manifest
- consistent `getOwners()` and `getThreshold()` results
- distinct, non-zero owner addresses
- a threshold between one and the owner-address count

An interface-only response or an unlisted singleton does not become a verified Safe. It remains contract evidence.

The dashboard displays thresholds as address evidence, such as `2/3 addresses`; it does not translate that into claims about people.

### 5.6 ERC-4337 decision and scan design

ERC-4337 classification requires positive `UserOperationEvent.sender` evidence from a versioned canonical EntryPoint listed in the checked-in manifest.

To prevent unbounded or misleading scans, the enrichment logic:

- clamps each EntryPoint range to its deployment block
- splits work into configurable block chunks
- batches sender topics
- retries only unresolved chunks
- retains successful ranges across retries
- records exact failed ranges
- reports partial rather than complete evidence when some chunks fail

A failed code lookup can still produce a partial result when another evidence source succeeded. `failed` is reserved for cases with no usable evidence source.

No full live account-enrichment run or historical backfill was performed as part of this feature.

### 5.7 Dashboard changes

The dashboard gained multi-select account-evidence filtering and badges for:

- EOA candidate
- delegated EOA
- Safe
- ERC-4337
- contract
- unknown

The graph and tables preserve independent Safe/ERC-4337 overlap. Unknown evidence remains visible instead of being silently converted into an EOA or contract claim.

Zero-address, configured-wallet, and token-contract ranking exclusions were preserved.

### 5.8 Validation reported by the agent

- Python compilation of the enrichment script
- `bunx tsc --noEmit`
- 26 Python label/enrichment tests at the time of the PR
- 94 analytics tests at the time of the PR
- full deterministic pipeline
- production dashboard build
- staged and pre-commit Codex review gates
- GitHub `Verify application`: passed

The PR changed 31 files with 3,123 insertions and 1,218 deletions. Much of the apparent churn came from extending the 1,000-row checked-in account-evidence seed to the new schema.

## 6. Feature 3: token-quality tiers

PR: [#15](https://github.com/ubabe53/evm-wallet-search/pull/15)  
Feature commits:

- `50373c0` — token-quality tiers
- `2d240d4` — composed token and account evidence
- `b52c126` — aligned token-ranking invariants

Merge commit: `30a942d3819db92c897bdb9f2f5658d514578799`

### 6.1 Problem being solved

The previous labeling allowed a token's presence in one registry to look stronger than it really was. That made low-quality tokens such as OSCAR or PUPPIES appear verified/trusted even though the only evidence could be one registry listing.

The solution separates three independent questions:

1. Is display metadata available?
2. How strong is the token-quality evidence?
3. Is there spam or suspicious-behavior evidence?

### 6.2 Token identity and evidence

Token identity remains `chain_id + token_address`. Symbols and names remain untrusted display attributes.

Registry matches use exact Ethereum contract addresses. Names or symbols are never used to merge identities.

The quality model records:

- `token_quality`
- source list
- source count
- reason
- provenance
- `token-quality-v1`

### 6.3 Quality tiers

The tiers are:

#### `high_confidence`

Requires either:

- reviewed manual approval, or
- exact-address membership in at least two independent registries

#### `listed`

Requires exact-address membership in exactly one registry.

#### `unknown`

Used when evidence is RPC-only or no registry/reviewed approval is present.

RPC-returned names, symbols, and decimals can improve display metadata, but they do not promote trust.

### 6.4 Reputation precedence

The effective token status follows this precedence:

1. Reviewed spam.
2. Automated suspected spam.
3. High-confidence trusted.
4. Otherwise unverified.

The classifier is versioned as `token-reputation-v2`.

Quality confidence and spam reputation remain separate. For example, good metadata does not override spam evidence, and lack of registry evidence does not prove spam.

### 6.5 OSCAR and PUPPIES regression cases

Two exact-address tests prevent single-registry tokens from being promoted to trusted:

- OSCAR: `0xebb66a88cedd12bfe3a289df6dfee377f2963f12`
- PUPPIES: `0xcf91b70017eabde82c9671e30e5502d312ea6eb2`

Both are expected to remain:

- quality: `listed`
- status: `unverified`

### 6.6 Dashboard and exporter changes

The dashboard now defaults to `high_confidence` quality, while `listed` and `unknown` remain selectable.

Status, quality, and account-evidence filters are composed before:

- token-flow calculations
- graph selection
- timeline calculations
- counterparty summaries
- pagination
- visible summary counts

The bounded export balances rows across status, quality, and account-evidence cells. It also carries complete counts, export limits, candidate-union metadata, and exact-ranking guarantees into `meta.json`.

No price, market-cap, volume, or liquidity API was added.

### 6.7 Validation reported by the agent

- full `bun run test`
- `bunx tsc --noEmit`
- production dashboard build
- configured pre-commit Codex review gate
- GitHub `Verify application`: passed
- advisory dependency audit: passed

The PR changed 29 files with 1,346 insertions and 205 deletions.

## 7. How the three features work together

The integrated pipeline now separates four different evidence dimensions:

| Dimension | Question answered | Example values |
|---|---|---|
| Transfer event | What did the token contract emit? | `Transfer.from`, `Transfer.to`, raw value |
| Transaction initiation | Who submitted the top-level transaction, when known? | sender relation, target relation, indirect marker |
| Counterparty account evidence | What address behavior/code was observed at a pinned block/range? | EOA candidate, delegated EOA, Safe, ERC-4337, contract, unknown |
| Token quality/reputation | How strong is token identity evidence, and is there spam evidence? | high confidence/listed/unknown plus trusted/unverified/suspected spam/spam |

This separation is the central design improvement. It avoids conclusions such as:

- “contract means not an account”
- “no code means a human-controlled EOA”
- “single registry listing means trusted”
- “transfer sender differs from transaction sender, therefore spam”
- “good metadata means legitimate token”

The dashboard can combine the dimensions for exploration without collapsing them into one unverifiable label.

## 8. GitHub and authorship record

All three feature commits were authored as:

```text
ubabe53 <umberto.wees@gmail.com>
```

GitHub-created merge commits were authored as:

```text
umberto <55484855+ubabe53@users.noreply.github.com>
```

Merged PRs and final CI state:

| PR | Merge commit | Merged at (UTC) | Verify application | Dependency audit |
|---|---|---|---|---|
| #14 | `51feba9` | 2026-07-19 14:32:07 | passed | passed |
| #16 | `67e40e6` | 2026-07-19 15:06:40 | passed | passed |
| #15 | `30a942d` | 2026-07-19 15:40:12 | passed | passed |

At the time of this report, local `main` and `origin/main` both point to `30a942d`.

## 9. Current local runtime state

### 9.1 Still running

- The three worktree-specific Codex CLI terminals are still open in Herdr.
- The local Vite dashboard process is still running at `http://127.0.0.1:5173/`.

### 9.2 Stopped

There is no active Vitalik-fixture generation, dbt build, or dashboard-export process.

The two large DuckDB temporary directories created by aborted all-history/90-day exports were moved to the macOS Trash rather than permanently deleted. They remain recoverable until the Trash is emptied.

## 10. Paused Vitalik 90-day fixture experiment

After the three PRs were merged, work began on replacing the six-row default dashboard fixture with real Vitalik data. This experiment is intentionally paused and is not committed.

### 10.1 What was learned

- Local HyperIndex Postgres contains 317,941 wallet-relevant ERC-20 transfers.
- The indexed source spans blocks 1,545,550–25,522,946.
- A complete 90-day slice contained 117,566 transfers and 2,712 token contracts.
- The complete slice compressed to a practical Parquet file, but the current exporter became the bottleneck.
- A full-history export generated roughly 3.5 GB of DuckDB temporary state before being stopped.
- The complete 90-day export generated roughly 6.2 GB of temporary state and was still running after more than four minutes, so it was stopped.
- Historical source rows do not contain the newly introduced top-level transaction sender/target fields. They must remain null/unknown; they cannot be reconstructed from the transfer log.
- A first Parquet attempt exposed scientific-notation conversion of large Postgres numerics. The generator was changed to cast `value_raw::text` inside Postgres before DuckDB reads it.

### 10.2 Current experimental direction

The uncommitted experiment was changed to a deterministic daily sample across a 90-day window, capped at 100 transfers per active UTC day and ordered by `md5(id), id` within each day. The latest generator run produced 2,931 rows.

This sample has not yet completed the full post-change validation cycle. In particular, analytics were successfully built for the earlier complete 117,566-row artifact, but the final 2,931-row sampled artifact has not yet been rebuilt and exported through the complete pipeline.

### 10.3 Uncommitted files

The main worktree currently contains uncommitted edits related to this paused experiment in:

- `README.md`
- `analytics/dbt_project.yml`
- `analytics/models/marts/pipeline_metadata.sql`
- `analytics/models/schema.yml`
- `analytics/models/staging/stg_counterparty_metadata.sql`
- `analytics/models/staging/stg_erc20_transfers.sql`
- `analytics/models/staging/stg_token_metadata.sql`
- `analytics/tests/transaction_initiation_fixture_evidence.sql`
- `docs/architecture.md`
- `docs/data-model.md`
- `docs/operations.md`
- `package.json`
- `scripts/export_dashboard.py`
- `scripts/run_dbt.py`
- `src/App.tsx`
- `src/data.ts`
- `tests/dashboard-smoke.test.tsx`
- new `analytics/fixtures/` files
- new `scripts/create_vitalik_fixture.py`

This report is also a new uncommitted file.

### 10.4 Decision needed when work resumes

Before continuing, choose one of these directions:

1. Keep the six-row semantic fixture as the default and add the Vitalik sample as an explicit local demo mode.
2. Make the Vitalik sample the default dashboard fixture while keeping the six-row fixture exclusively for CI/semantic tests.
3. Optimize or simplify the exact 6,615-filter-combination export contract so a complete 90-day source slice becomes practical.
4. Discard the paused fixture experiment and return the main worktree to the clean merged revision `30a942d`, preserving only this report if desired.

The safest next step is to decide this fixture/export contract before doing more implementation. The central question is whether the public demo should optimize for complete bounded history, representative sampled history, or exact filter-ranking guarantees; it should not imply all three simultaneously.

## 11. Suggested review path

For a quick review of the merged work:

1. Read sections 4–7 of this report for the semantic decisions.
2. Open the three linked PRs to inspect individual diffs and CI runs.
3. Run the dashboard and compare the status, quality, and account-evidence controls.
4. Inspect recent events with transaction sender/target evidence and indirect markers.
5. Inspect OSCAR and PUPPIES to confirm they are listed/unverified rather than trusted.
6. Inspect Safe/ERC-4337 overlap and unknown account evidence to verify the UI avoids personhood claims.
7. Decide the paused fixture/export direction in section 10.4 before resuming data work.
