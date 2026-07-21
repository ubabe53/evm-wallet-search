# Copilot instructions

## Project context

This repository is a locally run Ethereum wallet analytics application. Envio
HyperIndex captures the ERC-20-intended `Transfer(address,address,uint256)`
signature without currently disambiguating ERC-721, dbt transforms rows into DuckDB marts, and the
local FastAPI service executes read-only queries over the isolated live artifact.
The React/Vite dashboard selects the API adapter in local development and the
generated-JSON adapter only for the GitHub Pages fixture demo. Fixture tests and
demo builds must remain offline and reproducible; never enable both adapters together.

Use these commands when validating changes:

```sh
bun install --frozen-lockfile
bun run test
bun run dashboard:build
```

## Review priorities

- Focus on correctness, security, data provenance, regression risk, and missing
  tests. Avoid comments that are only stylistic or subjective.
- Never expose secrets, private RPC URLs, database credentials, `.env` files,
  `config.yaml`, DuckDB files, generated dashboard JSON, or indexer state.
- Ordinary tests and fixture analytics builds must not require internet access,
  Docker, an RPC provider, Envio credentials, or HyperIndex Postgres.
- Treat Ethereum addresses as case-insensitive exact identifiers. Never infer a
  token identity or trust status from only its name or symbol.
- Registry membership may supply trusted display metadata, but it is not a
  security guarantee. RPC metadata is self-declared and must never establish
  trust. Absence from a registry must remain neutral rather than imply spam.
- Only a reviewed manual override may assign final `spam`. Automated rules may
  assign internal `suspected_spam` only when their evidence and reason codes are
  preserved for audit. The dashboard merges both statuses into one `Spam` state.
- When classifier thresholds or reason rules change, require matching tests,
  classifier-version updates, and documentation changes.
- When a dbt mart or seed schema changes, verify the related dbt tests,
  `docs/data-model.md`, local API contract, frontend client types, fixture-demo
  exporter, and frontend tests as applicable.
- Treat material documentation drift as a correctness problem. Use `AGENTS.md`
  to route changes and `ARCHITECTURE.md` for system boundaries. When code shifts
  behavior, commands, architecture, data contracts, semantics, setup, or
  operations, require the owning document to change in the same PR. Do not
  demand documentation for behavior-preserving implementation details.
- DuckDB marts retain the complete local dataset. Local API queries must be
  bounded and paginated while returning complete matching counts and provenance.
  The production API must read only `analytics/artifacts/live.duckdb`, reject
  fixture provenance, use parameterized filters, and bind to loopback by default.
  Static JSON is a fixture-only demo and must report its provenance and limits in
  `meta.json`; do not expand full-history static precomputation.
- Dashboard changes must preserve accessibility, loading/error behavior, the
  default-off `Include spam` semantics, and both light and dark themes.
- Documentation must not claim behavior or architecture contradicted by the
  implementation.

When reviewing a pull request, explain the concrete failure mode and point to the
smallest relevant code location. Suggest a correction when one is clear. Do not
approve or merge changes automatically.
