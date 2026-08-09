import { describe, expect, test } from "vitest";
import {
  appPort,
  normalizeInitialWallet,
  parseEnvironmentFile,
  scanStage,
} from "../scripts/local_stack";

describe("local Docker stack launcher", () => {
  test("accepts and normalizes an address or ENS initial target", () => {
    expect(normalizeInitialWallet(" 0xA000000000000000000000000000000000000001 ")).toBe(
      "0xa000000000000000000000000000000000000001",
    );
    expect(normalizeInitialWallet("Example.ETH")).toBe("example.eth");
  });

  test("rejects an absent or malformed initial target", () => {
    expect(() => normalizeInitialWallet(undefined)).toThrow(/app:up/);
    expect(() => normalizeInitialWallet("not a wallet")).toThrow(/app:up/);
  });

  test("validates the loopback dashboard port", () => {
    expect(appPort({})).toBe(5173);
    expect(appPort({ EVM_WALLET_APP_PORT: "5180" })).toBe(5180);
    expect(() => appPort({ EVM_WALLET_APP_PORT: "80" })).toThrow(/1024/);
  });

  test("loads Compose settings from the ignored environment file", () => {
    expect(parseEnvironmentFile(`
      # local configuration
      ENVIO_API_TOKEN="secret-token"
      export EVM_WALLET_APP_PORT=5180
      ETHEREUM_RPC_URL='https://rpc.example'
    `)).toEqual({
      ENVIO_API_TOKEN: "secret-token",
      EVM_WALLET_APP_PORT: "5180",
      ETHEREUM_RPC_URL: "https://rpc.example",
    });
  });

  test("reports the same honest named scan stages as the dashboard", () => {
    expect(scanStage({ status: "queued", progress: 0 })).toBe("Queued");
    expect(scanStage({ status: "running", progress: 1 })).toBe("Preparing scan");
    expect(scanStage({ status: "running", progress: 5 })).toBe(
      "Indexing and building analytics",
    );
    expect(scanStage({ status: "running", progress: 95 })).toBe(
      "Validating and publishing",
    );
    expect(scanStage({ status: "completed", progress: 100 })).toBe("Complete");
  });
});
