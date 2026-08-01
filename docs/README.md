# Documentation

This directory owns the detailed, reviewed contracts for EVM Wallet Search. Keep the root
[README](../README.md) short and user-facing; put durable behavioral, data, and operational detail
in the contract that owns it.

## Canonical guides

| Document | Owns |
| --- | --- |
| [Architecture](architecture.md) | Product behavior, semantic policy, dashboard filtering, token recognition, and fixture-export policy |
| [Data model](data-model.md) | Model grains, keys, fields, classifications, provenance, API/export shapes, and tests |
| [Operations](operations.md) | Setup, credentials, commands, enrichment, recovery, verification, and delivery |
| [System map](../ARCHITECTURE.md) | Component boundaries, dependency direction, stable invariants, and known implementation gaps |
| [Agent guide](../AGENTS.md) | Working method, validation, and the routing table for synchronized documentation changes |

Field-level dbt contracts live beside the models in
[`analytics/models/`](../analytics/models/) and [`analytics/seeds/_seeds.yml`](../analytics/seeds/_seeds.yml).
They complement rather than replace [data-model.md](data-model.md), which also covers
Python-owned local tables and delivery contracts outside the dbt manifest.

## Editing boundary

- Link to a canonical definition instead of copying a detailed contract into a component README.
- Update documentation only when its owned behavior changes; do not mechanically rewrite unrelated
  context.
- Preserve the distinction between emitted Transfer-signature evidence and interpretation.
- Keep fixture/export limits visibly separate from finalized live coverage.
- Never present recognition or pinned-block account evidence as identity, reputation, or safety.

Use the routing table in [AGENTS.md](../AGENTS.md#change-routing) before changing a system
boundary, model contract, command, API shape, export shape, or visible dashboard behavior.

## Images

Screenshot placement and verification are documented in
[`images/README.md`](images/README.md). Do not link an expected filename from a public README
until the corresponding verified image exists.
