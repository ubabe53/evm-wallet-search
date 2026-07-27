import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const token = {
  wallet_id: "vitalik",
  wallet_address: "0x1",
  token_address: "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",
  token_symbol: "USDC",
  token_name: "USD Coin",
  token_decimals: 6,
  token_status: "trusted",
  recognition_status: "recognized",
  recognition_reason: "registry_match",
  recognition_source: "registry",
  recognition_version: "token-recognition-v1",
  recognition_override_status: null,
  metadata_source: "registry",
  metadata_source_url: null,
  metadata_availability: "complete",
  transfer_count: 1,
  inbound_transfer_count: 1,
  outbound_transfer_count: 0,
  indirect_inbound_transfer_count: 0,
  indirect_outbound_transfer_count: 0,
  counterparty_count: 1,
  sender_account_count: 1,
  recipient_account_count: 0,
  value_raw_sum: "1000000",
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("live token-recognition controls", () => {
  it("restores the exact prior override and expires Undo after four seconds", async () => {
    vi.stubEnv("VITE_DATA_MODE", "api");
    let override: "recognized" | "other" | null = null;
    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/v1/metadata") {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          ens: "vitalik.eth", wallet_address: "0x1", data_source: "hyperindex",
          generated_at: "2025-01-01T00:00:00Z", transfer_count: 1,
          account_evidence_population_scope: "distinct_nonzero_nonself_event_counterparties",
          account_evidence_eligible_address_count: 1,
          account_evidence_classified_address_count: 0,
          account_evidence_failed_address_count: 0,
          account_evidence_not_checked_address_count: 1,
          account_evidence_address_coverage_rate: 0,
          account_evidence_eligible_event_count: 1,
          account_evidence_classified_event_count: 0,
          account_evidence_failed_event_count: 0,
          account_evidence_not_checked_event_count: 1,
          account_evidence_event_coverage_rate: 0,
          account_evidence_observation_block_number_min: null,
          account_evidence_observation_block_number_max: null,
          account_evidence_observation_block_timestamp_min: null,
          account_evidence_observation_block_timestamp_max: null,
          is_sampled: false,
        }) });
      }
      if (input.startsWith("/api/v1/summary?")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          transfer_count: 1, token_count: 1, counterparty_count: 1,
        }) });
      }
      if (input.startsWith("/api/v1/events?")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          complete_matching_count: 0, returned_count: 0, next_cursor: null, items: [],
        }) });
      }
      if (input.startsWith("/api/v1/timeline?")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          interval: "month", complete_matching_count: 0, returned_count: 0, items: [],
        }) });
      }
      if (input.startsWith("/api/v1/tokens?")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          complete_matching_count: 1,
          returned_count: 1,
          items: [{
            ...token,
            recognition_status: override ?? token.recognition_status,
            recognition_source: override == null ? "registry" : "manual",
            recognition_override_status: override,
          }],
        }) });
      }
      if (input.startsWith("/api/v1/counterparties?")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          complete_matching_count: 0, returned_count: 0, items: [],
        }) });
      }
      if (input.endsWith("/recognition")) {
        const previous = override;
        override = init?.method === "DELETE"
          ? null
          : JSON.parse(String(init?.body)).status;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({
          token_address: token.token_address,
          automatic_status: "recognized",
          override_status: override,
          recognition_status: override ?? "recognized",
          recognition_source: override == null ? "automatic" : "manual",
          previous_override_status: previous,
        }) });
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { App } = await import("../src/App");
    render(<App />);
    const control = await screen.findByRole("combobox", { name: "Recognition for USDC" });

    fireEvent.change(control, { target: { value: "other" } });
    expect(await screen.findByRole("button", { name: "Undo" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) =>
      String(url).endsWith("/recognition") && init?.method === "DELETE")).toBe(true));
    expect(override).toBeNull();

    const refreshed = await screen.findByRole("combobox", { name: "Recognition for USDC" });
    vi.useFakeTimers();
    fireEvent.change(refreshed, { target: { value: "recognized" } });
    await act(async () => Promise.resolve());
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(3_999));
    expect(screen.getByRole("button", { name: "Undo" })).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole("button", { name: "Undo" })).not.toBeInTheDocument();
  });

  it("ignores an older recognition reload that resolves after a newer one", async () => {
    vi.stubEnv("VITE_DATA_MODE", "api");
    let override: "recognized" | "other" | null = null;
    let tokenReads = 0;
    let resolveOlderTokenRead: ((value: Response) => void) | undefined;
    const olderTokenRead = new Promise<Response>((resolve) => {
      resolveOlderTokenRead = resolve;
    });
    const ok = (payload: unknown) => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(payload),
    } as Response);
    const collection = (items: unknown[] = []) => ({
      complete_matching_count: items.length,
      returned_count: items.length,
      next_cursor: null,
      items,
    });
    const tokenPayload = (status: "recognized" | "other" | null) => collection([{
      ...token,
      recognition_status: status ?? token.recognition_status,
      recognition_source: status == null ? "registry" : "manual",
      recognition_override_status: status,
    }]);

    const fetchMock = vi.fn((input: string, init?: RequestInit) => {
      if (input === "/api/v1/metadata") {
        return ok({
          ens: "vitalik.eth", wallet_address: "0x1", data_source: "hyperindex",
          generated_at: "2025-01-01T00:00:00Z", transfer_count: 1,
          account_evidence_population_scope: "distinct_nonzero_nonself_event_counterparties",
          account_evidence_eligible_address_count: 1,
          account_evidence_classified_address_count: 0,
          account_evidence_failed_address_count: 0,
          account_evidence_not_checked_address_count: 1,
          account_evidence_address_coverage_rate: 0,
          account_evidence_eligible_event_count: 1,
          account_evidence_classified_event_count: 0,
          account_evidence_failed_event_count: 0,
          account_evidence_not_checked_event_count: 1,
          account_evidence_event_coverage_rate: 0,
          account_evidence_observation_block_number_min: null,
          account_evidence_observation_block_number_max: null,
          account_evidence_observation_block_timestamp_min: null,
          account_evidence_observation_block_timestamp_max: null,
          is_sampled: false,
        });
      }
      if (input.startsWith("/api/v1/summary?")) {
        return ok({ transfer_count: 1, token_count: 1, counterparty_count: 1 });
      }
      if (input.startsWith("/api/v1/events?") || input.startsWith("/api/v1/timeline?") ||
        input.startsWith("/api/v1/counterparties?")) {
        return ok(collection());
      }
      if (input.startsWith("/api/v1/tokens?")) {
        tokenReads += 1;
        const requestedOverride = override;
        if (tokenReads === 2) {
          return olderTokenRead;
        }
        return ok(tokenPayload(requestedOverride));
      }
      if (input.endsWith("/recognition")) {
        const previous = override;
        override = init?.method === "DELETE" ? null : JSON.parse(String(init?.body)).status;
        return ok({
          token_address: token.token_address,
          automatic_status: "recognized",
          override_status: override,
          recognition_status: override ?? "recognized",
          recognition_source: override == null ? "automatic" : "manual",
          previous_override_status: previous,
        });
      }
      throw new Error(`Unexpected request ${input}`);
    });
    vi.stubGlobal("fetch", fetchMock);

    const { App } = await import("../src/App");
    render(<App />);
    const initialControl = await screen.findByRole("combobox", { name: "Recognition for USDC" });
    fireEvent.change(initialControl, { target: { value: "other" } });
    await waitFor(() => expect(tokenReads).toBe(2));

    fireEvent.change(screen.getByRole("combobox", { name: "Recognition for USDC" }), {
      target: { value: "recognized" },
    });
    await waitFor(() => expect(tokenReads).toBe(3));
    await waitFor(() => expect(screen.getByRole("combobox", { name: "Recognition for USDC" }))
      .toHaveValue("recognized"));

    await act(async () => {
      resolveOlderTokenRead?.(await ok(tokenPayload("other")));
    });
    expect(screen.getByRole("combobox", { name: "Recognition for USDC" })).toHaveValue("recognized");
  });
});
