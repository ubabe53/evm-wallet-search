# Copilot review instructions

## Sources of truth

Read [AGENTS.md](../AGENTS.md) first and follow its workflow, semantic invariants, validation,
and change-routing rules. Use [ARCHITECTURE.md](../ARCHITECTURE.md) for the current system map and
boundaries, then consult the relevant detailed contract under [`docs/`](../docs/README.md).
When narrative and implementation disagree, verify behavior from the nearest code and tests and
flag material documentation drift.

## Review guidance

- Report only concrete correctness, security, data-integrity, regression, portability,
  materially missing-test, or material documentation-drift problems. Avoid subjective style
  comments.
- Explain the failure mode, point to the smallest relevant location, and suggest a correction
  when one is clear.
- Preserve the narrow evidence claim: a captured `Transfer(address,address,uint256)` log does not
  prove ERC-20 compliance, intent, ownership, legitimacy, transaction initiation, or historical
  account type.
- The current public token classification is only `Recognized` or `Other`, resolved from
  exact-address registry evidence and optional local manual overrides. Neither result is a
  reputation or safety claim; names, symbols, registry absence, RPC metadata, and wallet activity
  must not become trust signals.
- Check that live DuckDB/API results remain distinct from bounded fixture-demo output and that
  provenance, limits, complete matching counts, and sampling state remain honest.
- Reject changes that expose credentials, private RPC URLs, ignored configuration, DuckDB files,
  generated dashboard JSON, or indexer state.
- Ordinary fixture builds and deterministic tests must remain offline and must not require
  Docker, RPC, Envio credentials, or HyperIndex Postgres.
- For cross-layer changes, use the routing table in
  [AGENTS.md](../AGENTS.md#change-routing) to verify that owning contracts and nearest tests move
  with the implementation.

Do not approve, merge, or otherwise mutate a pull request. Review comments should stay scoped to
the proposed diff and its direct consequences.
