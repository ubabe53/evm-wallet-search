import { describe, expect, test } from "vitest";
import { requireExplicitRpc } from "../scripts/local_enrich";

describe("packaged account enrichment", () => {
  test("requires an explicit RPC instead of silently using the public fallback", () => {
    expect(() => requireExplicitRpc({})).toThrow(/ETHEREUM_RPC_URL/);
    expect(() => requireExplicitRpc({ ETHEREUM_RPC_URL: "  " })).toThrow(/ETHEREUM_RPC_URL/);
    expect(() => requireExplicitRpc({ ETHEREUM_RPC_URL: "https://rpc.example" })).not.toThrow();
  });
});
