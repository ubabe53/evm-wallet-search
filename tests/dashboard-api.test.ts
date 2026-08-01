import { afterEach, describe, expect, it, vi } from "vitest";
import {
  loadApiDashboardData,
  loadNextApiEvents,
  createScanJob,
  loadScanJob,
  loadWallets,
  resetTokenRecognition,
  setTokenRecognition,
  type DashboardQuery,
} from "../src/data";

const query: DashboardQuery = {
  walletAddress: null,
  recognition: "recognized",
  accountFilters: ["contract"],
  query: "usdc",
  counterpartyLimit: 10,
  timelineInterval: "month",
  timelineYear: 2026,
  startDate: "2026-07-01",
  endDate: "2026-08-01",
};

function response(payload: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
}

afterEach(() => vi.unstubAllGlobals());

describe("live dashboard API adapter", () => {
  it("uses typed scan-job and wallet-list contracts", async () => {
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/v1/scan-jobs") {
        expect(init?.method).toBe("POST");
        expect(init?.body).toBe(JSON.stringify({ wallet: "vitalik.eth" }));
        return response({ job_id: "job-1", status: "queued", wallet_address: "0x1" });
      }
      if (input === "/api/v1/scan-jobs/job-1") return response({ job_id: "job-1", status: "completed" });
      if (input === "/api/v1/wallets") return response({ items: [{ wallet_address: "0x1", label: "vitalik.eth", chain_id: 1, status: "completed" }] });
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    expect((await createScanJob("vitalik.eth")).job_id).toBe("job-1");
    expect((await loadScanJob("job-1")).status).toBe("completed");
    expect((await loadWallets()).items[0].label).toBe("vitalik.eth");
  });

  it("loads exact counts and bounded collections without static fixture files", async () => {
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/v1/metadata") {
        return response({
          configured_wallet_label: "vitalik.eth",
          wallet_address: "0xwallet",
          data_source: "hyperindex",
        });
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
      if (input.startsWith("/api/v1/timeline?")) {
        return response({
          interval: "month",
          year: 2026,
          complete_matching_count: 100_001,
          returned_count: 1,
          items: [{
            bucket_start: "2026-07-01",
            bucket_end: "2026-08-01",
            transfer_count: 100_001,
            inbound_transfer_count: 40_000,
            outbound_transfer_count: 60_001,
            self_transfer_count: 0,
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
    expect(result.timelineBuckets[0]).toMatchObject({
      bucket_start: "2026-07-01",
      transfer_count: 100_001,
      inbound_transfer_count: 40_000,
      outbound_transfer_count: 60_001,
      self_transfer_count: 0,
    });
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("data/"))).toBe(false);
    const summaryUrl = String(fetchMock.mock.calls.find(([url]) => String(url).startsWith("/api/v1/summary?"))?.[0]);
    expect(summaryUrl).toContain("recognition=recognized");
    expect(summaryUrl).toContain("account=contract");
    expect(summaryUrl).toContain("q=usdc");
    expect(summaryUrl).toContain("start=2026-07-01");
    expect(summaryUrl).toContain("end=2026-08-01");
    const timelineUrl = String(fetchMock.mock.calls.find(([url]) => String(url).startsWith("/api/v1/timeline?"))?.[0]);
    expect(timelineUrl).toContain("interval=month");
    expect(timelineUrl).toContain("year=2026");
    expect(timelineUrl).not.toContain("start=");
    expect(timelineUrl).not.toContain("end=");
  });

  it("continues event pagination with the opaque API cursor", async () => {
    const fetchMock = vi.fn((_input: string) => response({
      complete_matching_count: 12,
      returned_count: 2,
      next_cursor: null,
      items: [{
        transfer_id: "one",
      }],
    }));
    vi.stubGlobal("fetch", fetchMock);

    const page = await loadNextApiEvents(query, "opaque+/cursor");

    expect(String(fetchMock.mock.calls[0][0])).toContain("cursor=opaque%2B%2Fcursor");
    expect(page.items[0].transfer_id).toBe("one");
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
