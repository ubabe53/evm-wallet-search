import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loadApiDashboardData,
  loadNextApiEvents,
  resetTokenRecognition,
  setTokenRecognition,
  type DashboardQuery,
} from "../src/data";

const query: DashboardQuery = {
  recognition: "recognized",
  accountFilters: ["contract"],
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
            account_type: "contract", code_state: "contract_code",
            observation_block_timestamp: "2025-05-17T03:11:47+00:00",
            observation_block_number: 22_500_000,
            eip7702_delegation_target: null,
            evidence_fetch_status: "complete", evidence_reason_codes: "code_observed",
            transfer_count: 20, inbound_transfer_count: 5, outbound_transfer_count: 15,
            token_count: 3,
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
    expect(result.graphCounterpartyCount).toBe(750);
    expect(result.data.graph.nodes).toHaveLength(2);
    expect(result.data.graph.edges[0].data).toMatchObject({
      direction: "both",
      source: "wallet:0xwallet",
      target: "counterparty:0x1111111111111111111111111111111111111111",
      transferCount: 20,
      counterpartyTransferCount: 20,
      inboundTransferCount: 5,
      outboundTransferCount: 15,
      tokenCount: 3,
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("data/"))).toBe(false);
    const summaryUrl = String(fetchMock.mock.calls.find(([url]) => String(url).startsWith("/api/v1/summary?"))?.[0]);
    expect(summaryUrl).toContain("recognition=recognized");
    expect(summaryUrl).toContain("account=contract");
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

  it("persists and resets recognition overrides through typed mutation requests", async () => {
    const fetchMock = vi.fn((_input: string, init?: RequestInit) => response({
      token_address: "0xtoken",
      automatic_status: "recognized",
      override_status: init?.method === "DELETE" ? null : "other",
      recognition_status: init?.method === "DELETE" ? "recognized" : "other",
      recognition_source: init?.method === "DELETE" ? "automatic" : "manual",
      previous_override_status: init?.method === "DELETE" ? "other" : null,
    }));
    vi.stubGlobal("fetch", fetchMock);

    await setTokenRecognition("0xtoken", "other");
    await resetTokenRecognition("0xtoken");

    expect(fetchMock).toHaveBeenNthCalledWith(1, "/api/v1/tokens/0xtoken/recognition", expect.objectContaining({
      method: "PUT",
      body: JSON.stringify({ status: "other" }),
    }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/api/v1/tokens/0xtoken/recognition", expect.objectContaining({
      method: "DELETE",
    }));
  });
});
