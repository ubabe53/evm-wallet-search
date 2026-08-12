import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const firstWallet = "0x1111111111111111111111111111111111111111";
const secondWallet = "0x2222222222222222222222222222222222222222";

function response(payload: unknown) {
  return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
}

function metadata(walletAddress: string) {
  return {
    configured_wallet_label: walletAddress === firstWallet ? "first.eth" : "second.eth",
    wallet_address: walletAddress,
    chain_id: 1,
    data_source: "hyperindex",
    generated_at: "2026-08-09T12:00:00+00:00",
    snapshot_run_id: `run-${walletAddress}`,
    snapshot_start_block: 0,
    snapshot_end_block: 25_000_000,
    snapshot_end_block_hash: "0xabc",
    snapshot_finality_policy: "ethereum_finalized",
    snapshot_scope_version: "wallet-transfer-v1",
    transfer_count: 0,
    event_block_number_min: null,
    event_block_number_max: null,
    first_event_at: null,
    last_event_at: null,
    account_evidence_population_scope: "distinct_nonzero_nonself_event_counterparties",
    account_evidence_eligible_address_count: 0,
    account_evidence_classified_address_count: 0,
    account_evidence_failed_address_count: 0,
    account_evidence_not_checked_address_count: 0,
    account_evidence_eligible_event_count: 0,
    account_evidence_classified_event_count: 0,
    account_evidence_failed_event_count: 0,
    account_evidence_not_checked_event_count: 0,
    account_evidence_observation_block_number_min: null,
    account_evidence_observation_block_number_max: null,
    account_evidence_observation_block_timestamp_min: null,
    account_evidence_observation_block_timestamp_max: null,
    account_evidence_schema_version: null,
    api_schema_version: "dashboard-api-v16",
    database_mode: "live",
    completeness_scope: "finalized_block_range",
    indexer_checkpoint_recorded: true,
    finality_status: "finalized",
    is_sampled: false,
  };
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("live wallet controls", () => {
  it("switches completed wallets separately and clears an accepted scan input", async () => {
    vi.stubEnv("VITE_DATA_MODE", "api");
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/v1/scan-jobs/active") return response({ job: null });
      if (input === "/api/v1/wallets") {
        return response({
          items: [
            { chain_id: 1, wallet_address: firstWallet, label: "first.eth", status: "completed" },
            { chain_id: 1, wallet_address: secondWallet, label: "second.eth", status: "completed" },
          ],
        });
      }
      if (input.startsWith("/api/v1/metadata")) {
        return response(metadata(input.includes(encodeURIComponent(secondWallet)) ? secondWallet : firstWallet));
      }
      if (input.startsWith("/api/v1/summary?")) {
        return response({ transfer_count: 0, token_count: 0, counterparty_count: 0 });
      }
      if (input.startsWith("/api/v1/timeline?")) {
        return response({ interval: "year", year: null, complete_matching_count: 0, returned_count: 0, items: [] });
      }
      if (input.startsWith("/api/v1/events?") || input.startsWith("/api/v1/tokens?") || input.startsWith("/api/v1/counterparties?")) {
        return response({ complete_matching_count: 0, returned_count: 0, next_cursor: null, items: [] });
      }
      if (input === "/api/v1/scan-jobs" && init?.method === "POST") {
        return response({
          job_id: "job-1",
          requested_value: "new.eth",
          wallet_address: "0x3333333333333333333333333333333333333333",
          wallet_label: "new.eth",
          status: "queued",
          progress: 0,
          from_block: 0,
          to_block: 25_000_100,
          error: null,
          created_at: "2026-08-09T12:01:00+00:00",
          updated_at: "2026-08-09T12:01:00+00:00",
        });
      }
      if (input === "/api/v1/scan-jobs/job-1") {
        return new Promise(() => undefined);
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { App } = await import("../src/App");

    render(<App />);

    const walletSelect = await screen.findByRole("combobox", { name: "Analyzed wallet" });
    expect(walletSelect).toHaveValue(firstWallet);
    fireEvent.change(walletSelect, { target: { value: secondWallet } });
    await waitFor(() => expect(walletSelect).toHaveValue(secondWallet));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) =>
      String(url).includes(`wallet_address=${encodeURIComponent(secondWallet)}`),
    )).toBe(true));
    expect(fetchMock.mock.calls.some(([url, options]) =>
      url === "/api/v1/scan-jobs" && options?.method === "POST",
    )).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Scan wallet" }));
    const scanInput = screen.getByRole("textbox", { name: "Wallet address or ENS" });
    fireEvent.change(scanInput, { target: { value: "new.eth" } });
    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));

    await waitFor(() => expect(scanInput).toHaveValue(""));
    expect(screen.getByRole("button", { name: "Queued" })).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Queued" })).not.toHaveAttribute("value");
    expect(screen.queryByText("0%")).not.toBeInTheDocument();
    expect(screen.queryByText("Live mode")).not.toBeInTheDocument();
    expect(screen.queryByText("Completed wallets:")).not.toBeInTheDocument();
  });

  it("keeps the last loaded wallet visible and retries a failed switch", async () => {
    vi.stubEnv("VITE_DATA_MODE", "api");
    let failSecondWallet = true;
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/v1/scan-jobs/active") return response({ job: null });
      if (input === "/api/v1/wallets") {
        return response({
          items: [
            { chain_id: 1, wallet_address: firstWallet, label: "first.eth", status: "completed" },
            { chain_id: 1, wallet_address: secondWallet, label: "second.eth", status: "completed" },
          ],
        });
      }
      if (input.startsWith("/api/v1/metadata")) {
        if (input.includes(encodeURIComponent(secondWallet)) && failSecondWallet) {
          return Promise.resolve({
            ok: false,
            status: 503,
            json: () => Promise.resolve({ detail: "Wallet data temporarily unavailable" }),
          });
        }
        return response(metadata(input.includes(encodeURIComponent(secondWallet)) ? secondWallet : firstWallet));
      }
      if (input.startsWith("/api/v1/summary?")) {
        return response({ transfer_count: 0, token_count: 0, counterparty_count: 0 });
      }
      if (input.startsWith("/api/v1/timeline?")) {
        return response({ interval: "year", year: null, complete_matching_count: 0, returned_count: 0, items: [] });
      }
      if (input.startsWith("/api/v1/events?") || input.startsWith("/api/v1/tokens?") || input.startsWith("/api/v1/counterparties?")) {
        return response({ complete_matching_count: 0, returned_count: 0, next_cursor: null, items: [] });
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { App } = await import("../src/App");

    render(<App />);

    const walletSelect = await screen.findByRole("combobox", { name: "Analyzed wallet" });
    fireEvent.change(walletSelect, { target: { value: secondWallet } });

    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("Wallet data temporarily unavailable");
    expect(notice).toHaveTextContent("Showing the last loaded results for first.eth");
    expect(walletSelect).toHaveValue(firstWallet);
    expect(screen.getByRole("region", { name: "Analysis context" })).toHaveTextContent("0x111...111");
    expect(screen.queryByText(/Build live analytics/)).not.toBeInTheDocument();

    failSecondWallet = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    await waitFor(() => expect(walletSelect).toHaveValue(secondWallet));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("refreshes completed wallets with a signal independent from scan polling", async () => {
    vi.stubEnv("VITE_DATA_MODE", "api");
    const newWallet = "0x3333333333333333333333333333333333333333";
    let walletRequestCount = 0;
    let refreshSignal: AbortSignal | undefined;
    let resolveWalletRefresh: (() => void) | undefined;
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/v1/scan-jobs/active") return response({ job: null });
      if (input === "/api/v1/wallets") {
        walletRequestCount += 1;
        if (walletRequestCount === 1) {
          return response({
            items: [{ chain_id: 1, wallet_address: firstWallet, label: "first.eth", status: "completed" }],
          });
        }
        refreshSignal = init?.signal ?? undefined;
        return new Promise((resolve) => {
          resolveWalletRefresh = () => resolve({
            ok: true,
            json: () => Promise.resolve({
              items: [
                { chain_id: 1, wallet_address: firstWallet, label: "first.eth", status: "completed" },
                { chain_id: 1, wallet_address: newWallet, label: "new.eth", status: "completed" },
              ],
            }),
          });
        });
      }
      if (input.startsWith("/api/v1/metadata")) {
        return response({
          ...metadata(input.includes(encodeURIComponent(newWallet)) ? newWallet : firstWallet),
          configured_wallet_label: input.includes(encodeURIComponent(newWallet)) ? "new.eth" : "first.eth",
        });
      }
      if (input.startsWith("/api/v1/summary?")) {
        return response({ transfer_count: 0, token_count: 0, counterparty_count: 0 });
      }
      if (input.startsWith("/api/v1/timeline?")) {
        return response({ interval: "year", year: null, complete_matching_count: 0, returned_count: 0, items: [] });
      }
      if (input.startsWith("/api/v1/events?") || input.startsWith("/api/v1/tokens?") || input.startsWith("/api/v1/counterparties?")) {
        return response({ complete_matching_count: 0, returned_count: 0, next_cursor: null, items: [] });
      }
      if (input === "/api/v1/scan-jobs" && init?.method === "POST") {
        return response({
          job_id: "job-completes",
          requested_value: "new.eth",
          wallet_address: newWallet,
          wallet_label: "new.eth",
          status: "queued",
          progress: 0,
          from_block: 0,
          to_block: 25_000_100,
          error: null,
          created_at: "2026-08-09T12:01:00+00:00",
          updated_at: "2026-08-09T12:01:00+00:00",
        });
      }
      if (input === "/api/v1/scan-jobs/job-completes") {
        return response({
          job_id: "job-completes",
          requested_value: "new.eth",
          wallet_address: newWallet,
          wallet_label: "new.eth",
          status: "completed",
          progress: 100,
          from_block: 0,
          to_block: 25_000_100,
          error: null,
          created_at: "2026-08-09T12:01:00+00:00",
          updated_at: "2026-08-09T12:02:00+00:00",
        });
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { App } = await import("../src/App");

    render(<App />);

    const walletSelect = await screen.findByRole<HTMLSelectElement>("combobox", { name: "Analyzed wallet" });
    fireEvent.click(screen.getByRole("button", { name: "Scan wallet" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Wallet address or ENS" }), {
      target: { value: "new.eth" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Start scan" }));

    await waitFor(() => expect(refreshSignal).toBeDefined());
    await new Promise((resolve) => window.setTimeout(resolve, 10));
    expect(refreshSignal?.aborted).toBe(false);

    resolveWalletRefresh?.();
    await waitFor(() => expect(
      Array.from(walletSelect.options).find((option) => option.value === newWallet)?.textContent,
    ).toContain("new.eth"));
  });

  it("shows a discovered first scan instead of the unavailable-artifact error", async () => {
    vi.stubEnv("VITE_DATA_MODE", "api");
    const activeJob = {
      job_id: "first-scan",
      requested_value: "first.eth",
      wallet_address: firstWallet,
      wallet_label: "first.eth",
      status: "running",
      progress: 5,
      from_block: 0,
      to_block: 25_000_000,
      error: null,
      created_at: "2026-08-12T08:00:00+00:00",
      updated_at: "2026-08-12T08:00:05+00:00",
    } as const;
    const fetchMock = vi.fn((input: string) => {
      if (input === "/api/v1/scan-jobs/active") return response({ job: activeJob });
      if (input === "/api/v1/wallets") return response({ items: [] });
      if (input === "/api/v1/scan-jobs/first-scan") return new Promise(() => undefined);
      if (input.startsWith("/api/v1/metadata")) {
        return Promise.resolve({
          ok: false,
          status: 503,
          json: () => Promise.resolve({ detail: "Analytics database unavailable" }),
        });
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { App } = await import("../src/App");

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Building wallet analytics" }))
      .toBeInTheDocument();
    expect(screen.getByText("first.eth")).toBeInTheDocument();
    expect(screen.getByRole("progressbar", { name: "Indexing and building analytics" }))
      .not.toHaveAttribute("value");
    expect(screen.getByText("Blocks 0–25,000,000")).toBeInTheDocument();
    expect(screen.queryByText(/Build live analytics/)).not.toBeInTheDocument();
  });
});
