# Copilot instructions

## Project context

This repository is a batch-oriented Ethereum wallet analytics application. Envio
HyperIndex captures ERC20 transfers, dbt transforms them into DuckDB marts, a
Python exporter writes bounded static JSON, and a React/Vite dashboard displays
the result. Fixture mode is the default and must remain offline and reproducible.

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
  assign `suspected_spam` only when their evidence and reason codes are exported.
- When classifier thresholds or reason rules change, require matching tests,
  classifier-version updates, and documentation changes.
- When a dbt mart or seed schema changes, verify the related dbt tests,
  `docs/data-model.md`, `src/data.ts`, the exporter, and frontend tests together.
- Preserve deterministic, status-balanced export limits. DuckDB marts retain the
  complete dataset; static JSON is a bounded browser view and must report its
  provenance and limits in `meta.json`.
- Dashboard changes must preserve accessibility, loading/error behavior, status
  filtering semantics, and both light and dark themes.
- Documentation describing behavior must change in the same pull request as the
  behavior itself.

When reviewing a pull request, explain the concrete failure mode and point to the
smallest relevant code location. Suggest a correction when one is clear. Do not
approve or merge changes automatically.
