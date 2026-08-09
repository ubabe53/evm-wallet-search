# Indexer

This component owns the Envio HyperIndex capture boundary for Ethereum mainnet. It records one
normalized `Erc20Transfer` entity for each configured-wallet
`Transfer(address,address,uint256)` log selected by the wildcard contract filter.

Despite the entity and contract names, the source is only ERC-20-intended. ERC-721 emits the
same signature, and this component does not disambiguate standards. It also does not collect
native ETH transfers, traces, internal calls, approvals, or arbitrary wallets.

## Important files

| File | Responsibility |
| --- | --- |
| [`config.yaml`](config.yaml) | Chain, wildcard event, topic filter, and selected transaction fields |
| [`schema.graphql`](schema.graphql) | Persisted entity contract, including canonical block and event ordering evidence |
| [`src/handlers/Erc20Transfer.ts`](src/handlers/Erc20Transfer.ts) | Handler registration and entity write |
| [`src/transferEntity.ts`](src/transferEntity.ts) | Exact event-to-entity normalization |
| [`src/wallets.ts`](src/wallets.ts) | Configured wallet addresses used by topic filters |

HyperIndex Postgres is ingestion persistence. It is read-only to dbt and is not a browser or
application query interface.

## Commands

Run commands from the repository root:

```sh
bun run indexer:codegen
bun run indexer:dev
```

`indexer:dev` requires Docker and an `ENVIO_API_TOKEN` supplied through the shell or ignored
`config.yaml`. Regenerate types after changing Envio field selection or the entity schema.
Schema changes that affect existing entity rows may require an explicit restart/reindex; ordinary
fixture builds never perform that work.

The worker-only bounded entrypoint accepts one canonical wallet, inclusive caller-validated block
range, temporary Postgres schema, and non-default indexer port:

```sh
bun run indexer:scan -- \
  --wallet 0x0000000000000000000000000000000000000001 \
  --from-block 100 --to-block 200 \
  --schema wallet_scan_example --indexer-port 8082
```

It generates an ignored temporary Envio config with `start_block` and `end_block`, supplies the
wallet to the topic filter at runtime, and runs `envio start --restart` only against the validated
`wallet_scan_*` schema. It assumes the local Envio Postgres/Hasura environment is already running.
This command alone does not publish analytics or merge the isolated rows; the wallet scan worker
owns those later steps. Never use `public` or another persistent schema for a bounded restart.
The entrypoint validates address/range syntax but does not contact Ethereum RPC or prove finality;
the scan-job caller must pin and verify the end block/hash before invoking it.

## Contracts

- [High-level component and trust boundaries](../ARCHITECTURE.md)
- [Detailed pipeline and source semantics](../docs/architecture.md#flow)
- [Staged event grain and exact-value policy](../docs/data-model.md#stg_transfer_events)
- [HyperIndex setup and replay guidance](../docs/operations.md#hyperindex-mode)

Indexer changes that alter scope, fields, or evidence semantics must update the owning contracts
and nearest tests in the same change.
