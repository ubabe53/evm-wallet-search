import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  App,
  counterpartyNodeSize,
  etherscanAddressUrl,
  etherscanTokenUrl,
  etherscanTransactionUrl,
  interactionEdgeLabel,
} from "../src/App";

const graph = {
  nodes: [
    { data: { id: "wallet:0x1", label: "vitalik.eth\nwallet", type: "wallet", address: "0x1", tokenAddress: null, symbol: null, addressType: "wallet" } },
    { data: { id: "token:0x2", label: "USDC", type: "token", address: null, tokenAddress: "0x2", symbol: "USDC", addressType: null } },
    { data: { id: "counterparty:0x1111111111111111111111111111111111111111", label: "0x1111...1111\ncontract", type: "counterparty", address: "0x1111111111111111111111111111111111111111", tokenAddress: null, symbol: null, addressType: "contract" } },
    { data: { id: "token:0x3", label: "SPAM", type: "token", address: null, tokenAddress: "0x3", symbol: "SPAM", addressType: null } },
    { data: { id: "counterparty:0x2222222222222222222222222222222222222222", label: "0x2222...2222\nwallet", type: "counterparty", address: "0x2222222222222222222222222222222222222222", tokenAddress: null, symbol: null, addressType: "wallet" } },
  ],
  edges: [
    { data: { id: "edge:1", interactionId: "interaction:0x1:0x1111111111111111111111111111111111111111:0x2:in", edgeRole: "token_counterparty", source: "counterparty:0x1111111111111111111111111111111111111111", target: "token:0x2", walletAddress: "0x1", counterpartyAddress: "0x1111111111111111111111111111111111111111", direction: "in", tokenAddress: "0x2", tokenSymbol: "USDC", tokenStatus: "trusted", metadataSource: "manual", metadataSourceUrl: "https://example.com/usdc", transferCount: 1, counterpartyTransferCount: 1, amountDecimalSum: 125 } },
    { data: { id: "edge:2", interactionId: "interaction:0x1:0x1111111111111111111111111111111111111111:0x2:in", edgeRole: "wallet_token", source: "token:0x2", target: "wallet:0x1", walletAddress: "0x1", counterpartyAddress: "0x1111111111111111111111111111111111111111", direction: "in", tokenAddress: "0x2", tokenSymbol: "USDC", tokenStatus: "trusted", metadataSource: "manual", metadataSourceUrl: "https://example.com/usdc", transferCount: 1, counterpartyTransferCount: 1, amountDecimalSum: 125 } },
    { data: { id: "edge:3", interactionId: "interaction:0x1:0x2222222222222222222222222222222222222222:0x3:in", edgeRole: "token_counterparty", source: "counterparty:0x2222222222222222222222222222222222222222", target: "token:0x3", walletAddress: "0x1", counterpartyAddress: "0x2222222222222222222222222222222222222222", direction: "in", tokenAddress: "0x3", tokenSymbol: "SPAM", tokenStatus: "spam", metadataSource: "manual", metadataSourceUrl: "https://example.com/spam", transferCount: 1, counterpartyTransferCount: 1, amountDecimalSum: 1 } },
    { data: { id: "edge:4", interactionId: "interaction:0x1:0x2222222222222222222222222222222222222222:0x3:in", edgeRole: "wallet_token", source: "token:0x3", target: "wallet:0x1", walletAddress: "0x1", counterpartyAddress: "0x2222222222222222222222222222222222222222", direction: "in", tokenAddress: "0x3", tokenSymbol: "SPAM", tokenStatus: "spam", metadataSource: "manual", metadataSourceUrl: "https://example.com/spam", transferCount: 1, counterpartyTransferCount: 1, amountDecimalSum: 1 } },
  ],
};

const summaries = {
  tokens: [
    {
      wallet_id: "vitalik",
      wallet_address: "0x1",
      token_address: "0x2",
      token_symbol: "USDC",
      token_name: "USD Coin",
      token_decimals: 6,
      token_status: "trusted",
      metadata_source: "manual",
      metadata_source_url: "https://example.com/usdc",
      token_label_reason: "Canonical metadata",
      direction: "in",
      transfer_count: 1,
      amount_decimal_sum: 125,
      value_raw_sum: "125000000",
    },
    {
      wallet_id: "vitalik", wallet_address: "0x1", token_address: "0x3", token_symbol: "SPAM",
      token_name: "Spam Token", token_decimals: 18, token_status: "spam", metadata_source: "manual",
      metadata_source_url: "https://example.com/spam", token_label_reason: "Test spam", direction: "in",
      transfer_count: 1, amount_decimal_sum: 1, value_raw_sum: "1000000000000000000",
    },
  ],
  counterparties: [],
};

const timeline = [{ wallet_id: "vitalik", wallet_address: "0x1", block_date: "2023-11-14", token_address: "0x2", token_symbol: "USDC", token_status: "trusted", metadata_source: "manual", metadata_source_url: "https://example.com/usdc", direction: "in", transfer_count: 1, amount_decimal_sum: 125, value_raw_sum: "125000000" }];

const events = [
  {
    transfer_id: "1-0xaaa-0",
    chain_id: 1,
    block_number: 17_000_001,
    block_timestamp: "2023-11-14T22:15:00+00:00",
    block_date: "2023-11-14",
    transaction_hash: "0xaaa",
    transaction_index: 2,
    log_index: 0,
    wallet_id: "vitalik",
    ens: "vitalik.eth",
    wallet_address: "0x1",
    direction: "in",
    counterparty_address: "0x1111111111111111111111111111111111111111",
    counterparty_type: "contract",
    token_address: "0x2",
    token_symbol: "USDC",
    token_name: "USD Coin",
    token_decimals: 6,
    token_status: "trusted",
    metadata_source: "manual",
    metadata_source_url: "https://example.com/usdc",
    token_label_reason: "Canonical metadata",
    value_raw: "125000000",
    amount_decimal: 125,
  },
  {
    transfer_id: "1-0xspam-0", chain_id: 1, block_number: 17_000_002,
    block_timestamp: "2023-11-14T22:16:00+00:00", block_date: "2023-11-14",
    transaction_hash: "0xspam", transaction_index: 3, log_index: 0, wallet_id: "vitalik",
    ens: "vitalik.eth", wallet_address: "0x1", direction: "in",
    counterparty_address: "0x2222222222222222222222222222222222222222", token_address: "0x3",
    counterparty_type: "wallet",
    token_symbol: "SPAM", token_name: "Spam Token", token_decimals: 18, token_status: "spam",
    metadata_source: "manual", metadata_source_url: "https://example.com/spam", token_label_reason: "Test spam",
    value_raw: "1000000000000000000", amount_decimal: 1,
  },
];

const metadata = {
  wallet_id: "vitalik",
  ens: "vitalik.eth",
  wallet_address: "0x1",
  chain_id: 1,
  data_source: "fixture",
  generated_at: "2023-11-14T22:15:00+00:00",
  transfer_count: 2,
  token_count: 2,
  counterparty_count: 2,
  non_spam_transfer_count: 1,
  non_spam_token_count: 1,
  non_spam_counterparty_count: 1,
  spam_transfer_count: 1,
  spam_token_count: 1,
  interaction_count: 2,
  token_summary_row_count: 2,
  counterparty_summary_row_count: 0,
  timeline_row_count: 1,
  first_event_at: "2023-11-14T22:15:00+00:00",
  last_event_at: "2023-11-14T22:15:00+00:00",
  status_counts: {
    trusted: { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    unverified: { transfer_count: 0, token_count: 0, counterparty_count: 0 },
    spam: { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "trusted+unverified": { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "trusted+spam": { transfer_count: 2, token_count: 2, counterparty_count: 2 },
    "unverified+spam": { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "trusted+unverified+spam": { transfer_count: 2, token_count: 2, counterparty_count: 2 },
  },
  exported_event_count: 2,
  exported_interaction_count: 2,
  exported_token_summary_count: 2,
  exported_counterparty_summary_count: 0,
  exported_timeline_row_count: 1,
  event_export_limit_per_status: 1000,
  graph_interaction_export_limit_per_status: 250,
  token_summary_export_limit_per_status: 500,
  counterparty_summary_export_limit: 500,
  timeline_row_export_limit: 5000,
  is_sampled: false,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("scales counterparty nodes gradually on a stable logarithmic range", () => {
    expect([1, 10, 100, 1_000, 10_000, 100_000].map(counterpartyNodeSize)).toEqual([26, 37, 47, 58, 68, 68]);
  });

  it("labels graph interactions with token and transfer count", () => {
    expect(interactionEdgeLabel("USDC", 5)).toBe("USDC x5");
    expect(interactionEdgeLabel("DAI", 12_500)).toBe("DAI x12,500");
  });

  it("builds canonical Etherscan routes", () => {
    expect(etherscanAddressUrl("0xabc")).toBe("https://etherscan.io/address/0xabc");
    expect(etherscanTokenUrl("0xdef")).toBe("https://etherscan.io/token/0xdef");
    expect(etherscanTransactionUrl("0x123")).toBe("https://etherscan.io/tx/0x123");
  });

  it("renders exported dashboard data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((path: string) => {
        const payload = path.endsWith("graph.json")
          ? graph
          : path.endsWith("summaries.json")
            ? summaries
            : path.endsWith("timeline.json")
              ? timeline
              : path.endsWith("meta.json")
                ? metadata
                : events;

        return Promise.resolve({ ok: true, json: () => Promise.resolve(payload) });
      }),
    );

    render(<App />);

    await waitFor(() => expect(screen.getByText("ERC20 token flow analytics for vitalik.eth")).toBeInTheDocument());
    expect(screen.getAllByText("USDC").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "USDC" })[0]).toHaveAttribute(
      "href",
      "https://etherscan.io/token/0x2",
    );
    expect(screen.getByRole("link", { name: "0x1111...1111" })).toHaveAttribute(
      "href",
      "https://etherscan.io/address/0x1111111111111111111111111111111111111111",
    );
    expect(screen.getByText("contract")).toHaveAttribute(
      "title",
      "Contract bytecode exists at the pinned Ethereum block",
    );
    expect(screen.getByRole("link", { name: "View transaction on Etherscan" })).toHaveAttribute(
      "href",
      "https://etherscan.io/tx/0xaaa",
    );
    expect(screen.getByText("Recent Events")).toBeInTheDocument();
    expect(screen.getByText("Fixture data")).toBeInTheDocument();
    expect(screen.getByLabelText("Maximum graph interactions")).toHaveValue("25");
    expect(screen.getByText("1 of 1 events")).toBeInTheDocument();
    expect(screen.getByLabelText("Include spam")).not.toBeChecked();
    fireEvent.click(screen.getByText("Status (2)"));
    const trustedStatus = screen.getByRole("checkbox", { name: "trusted" });
    const unverifiedStatus = screen.getByRole("checkbox", { name: "unverified" });
    const suspectedStatus = screen.getByRole("checkbox", { name: "suspected spam" });
    const spamStatus = screen.getByRole("checkbox", { name: "spam" });
    expect(trustedStatus).toBeChecked();
    expect(unverifiedStatus).toBeChecked();
    expect(suspectedStatus).toBeDisabled();
    expect(spamStatus).toBeDisabled();
    fireEvent.click(trustedStatus);
    expect(screen.queryByText("USDC")).not.toBeInTheDocument();
    fireEvent.click(trustedStatus);
    expect(screen.queryByText("SPAM")).not.toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Include spam"));
    expect(suspectedStatus).toBeEnabled();
    expect(suspectedStatus).toBeChecked();
    expect(spamStatus).toBeEnabled();
    expect(spamStatus).toBeChecked();
    expect(screen.getAllByText("SPAM").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "contract" } });
    expect(screen.getByRole("link", { name: "0x1111...1111" })).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "0x1111" } });
    expect(screen.getByText("0x1111...1111")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "0xaaa" } });
    expect(screen.getByText("2 nodes / 1 edges")).toBeInTheDocument();

    const graphElement = screen.getByRole("img", { name: /wallet interaction graph/i });
    const graphShell = graphElement.parentElement;
    expect(graphShell).toHaveAttribute("data-graph-theme", "light");

    fireEvent.click(screen.getByLabelText("Switch to dark theme"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(graphElement).toBe(screen.getByRole("img", { name: /wallet interaction graph/i }));
    expect(graphShell).toHaveAttribute("data-graph-theme", "dark");

    fireEvent.click(screen.getByLabelText("Switch to light theme"));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(graphElement).toBe(screen.getByRole("img", { name: /wallet interaction graph/i }));
    expect(graphShell).toHaveAttribute("data-graph-theme", "light");
  });

  it("shows an actionable error when generated data is unavailable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve({ ok: false, status: 404 })),
    );

    render(<App />);

    expect(await screen.findByText(/Could not load data\/graph\.json \(HTTP 404\)/)).toBeInTheDocument();
    expect(screen.getByText(/analytics:build/)).toBeInTheDocument();
  });
});
