import { afterEach, describe, expect, it, vi } from "vitest";
import { loadApiDashboardData, loadNextApiEvents, type DashboardQuery } from "../src/data";

const query: DashboardQuery = {
  includeSpam: false,
  accountFilters: ["contract", "safe"],
  query: "usdc",
  graphLimit: 25,
  counterpartyLimit: 10,
};

function response(payload: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
}

afterEach(() => vi.unstubAllGlobals());

describe("live dashboard API adapter", () => {
  it("loads exact counts and bounded collections without static fixture files", async () => {
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/v1/metadata") {
        return response({ ens: "vitalik.eth", wallet_address: "0xwallet", data_source: "hyperindex" });
      }
      if (input.startsWith("/api/v1/summary?")) {
        return response({ transfer_count: 100_001, token_count: 501, counterparty_count: 2_000 });
      }
      if (input.startsWith("/api/v1/events?")) {
        return response({ complete_matching_count: 100_001, returned_count: 0, next_cursor: "next", items: [] });
      }
      if (input.startsWith("/api/v1/tokens?")) {
        return response({ complete_matching_count: 501, returned_count: 0, items: [] });
      }
      if (input.startsWith("/api/v1/counterparties?")) {
        return response({ complete_matching_count: 2_000, returned_count: 0, items: [] });
      }
      if (input.startsWith("/api/v1/graph?")) {
        return response({
          complete_matching_count: 750,
          returned_count: 1,
          items: [{
            wallet_id: "vitalik", ens: "vitalik.eth", wallet_address: "0xwallet",
            counterparty_address: "0x1111111111111111111111111111111111111111",
            token_address: "0xtoken", token_symbol: "USDC", token_status: "trusted",
            direction: "in", account_type: "contract", is_safe: false,
            is_erc4337_account: false, observation_block_number: 22_500_000,
            eip7702_delegation_target: null, safe_version: null, safe_owner_count: null,
            safe_threshold: null, erc4337_entrypoint_version: null,
            erc4337_effective_coverage: null, erc4337_failed_ranges: null,
            evidence_coverage_start_block: 17_000_000, evidence_coverage_end_block: 22_500_000,
            transfer_count: 5, counterparty_transfer_count: 20,
          }],
        });
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await loadApiDashboardData(query);

    expect(result.summary.transfer_count).toBe(100_001);
    expect(result.eventCount).toBe(100_001);
    expect(result.tokenCount).toBe(501);
    expect(result.counterpartyCount).toBe(2_000);
    expect(result.graphInteractionCount).toBe(750);
    expect(result.data.graph.nodes).toHaveLength(2);
    expect(result.data.graph.edges[0].data).toMatchObject({
      direction: "in",
      source: "counterparty:0x1111111111111111111111111111111111111111",
      target: "wallet:0xwallet",
      transferCount: 5,
      counterpartyTransferCount: 20,
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("data/"))).toBe(false);
    const summaryUrl = String(fetchMock.mock.calls.find(([url]) => String(url).startsWith("/api/v1/summary?"))?.[0]);
    expect(summaryUrl).toContain("include_spam=false");
    expect(summaryUrl).toContain("account=contract");
    expect(summaryUrl).toContain("account=safe");
    expect(summaryUrl).toContain("q=usdc");
  });

  it("continues event pagination with the opaque API cursor", async () => {
    const fetchMock = vi.fn((_input: string) => response({
      complete_matching_count: 12,
      returned_count: 2,
      next_cursor: null,
      items: [{ transfer_id: "one", amount_decimal: "1.25" }, { transfer_id: "two", amount_decimal: null }],
    }));
    vi.stubGlobal("fetch", fetchMock);

    const page = await loadNextApiEvents(query, "opaque+/cursor");

    expect(String(fetchMock.mock.calls[0][0])).toContain("cursor=opaque%2B%2Fcursor");
    expect(page.items.map((item) => item.amount_decimal)).toEqual([1.25, null]);
  });

  it("represents an empty account selection explicitly", async () => {
    const fetchMock = vi.fn((_input: string) => response({
      complete_matching_count: 0,
      returned_count: 0,
      next_cursor: null,
      items: [],
    }));
    vi.stubGlobal("fetch", fetchMock);

    await loadNextApiEvents({ ...query, accountFilters: [] }, "cursor");

    expect(String(fetchMock.mock.calls[0][0])).toContain("account=none");
  });
});
