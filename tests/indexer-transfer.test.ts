import { createTestIndexer } from "envio";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import "../indexer/src/handlers/Erc20Transfer";
import { toErc20TransferEntity } from "../indexer/src/transferEntity";

describe("toErc20TransferEntity", () => {
  it("creates a deterministic one-row-per-transfer entity", () => {
    const entity = toErc20TransferEntity({
      chainId: 1,
      block: { number: 123n, timestamp: 1_700_000_000 },
      transaction: {
        hash: "0xABCDEF",
        transactionIndex: 4,
      },
      logIndex: 7,
      srcAddress: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
      params: {
        from: "0xD8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
        to: "0x000000000000000000000000000000000000dEaD",
        value: 2500000n,
      },
    });

    expect(entity).toEqual({
      id: "1-0xabcdef-7",
      chainId: 1,
      blockNumber: 123n,
      blockTimestamp: 1_700_000_000,
      transactionHash: "0xabcdef",
      transactionIndex: 4,
      logIndex: 7,
      tokenAddress: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
      fromAddress: "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
      toAddress: "0x000000000000000000000000000000000000dead",
      valueRaw: 2500000n,
    });
  });

  it("runs the registered HyperIndex handler with a simulated Transfer", async () => {
    const originalDirectory = process.cwd();
    process.chdir(join(originalDirectory, "indexer"));

    try {
      const testIndexer = createTestIndexer();
      const result = await testIndexer.process({
        chains: {
          1: {
            simulate: [
              {
                contract: "ERC20",
                event: "Transfer",
                srcAddress: "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
                logIndex: 7,
                block: { number: 123, timestamp: 1_700_000_000 },
                transaction: { hash: "0xABCDEF", transactionIndex: 4 },
                params: {
                  from: "0xD8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
                  to: "0x000000000000000000000000000000000000dEaD",
                  value: 2_500_000n,
                },
              },
            ],
          },
        },
      });

      expect(result.changes[0]?.Erc20Transfer?.sets?.[0]).toMatchObject({
        id: "1-0xabcdef-7",
        transactionIndex: 4,
        tokenAddress: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
        valueRaw: 2_500_000n,
      });
    } finally {
      process.chdir(originalDirectory);
    }
  });
});
