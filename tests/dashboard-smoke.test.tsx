import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  App,
  accountMatches,
  aggregateCounterparties,
  counterpartyNodeSize,
  etherscanAddressUrl,
  etherscanTokenUrl,
  etherscanTransactionUrl,
  interactionEdgeLabel,
  INDIRECT_TRANSFER_EXPLANATION,
} from "../src/App";
import type { CounterpartySummary } from "../src/data";

const contractAccountEvidence = {
  account_type: "contract",
  code_state: "contract_code",
  code_size_bytes: 32,
  observation_block_number: 17_006_000,
  observation_block_timestamp: "2023-11-18T12:00:00+00:00",
  eip7702_delegation_target: null,
  is_safe: false,
  safe_verification_status: "singleton_not_official",
  safe_version: null,
  safe_singleton_address: null,
  safe_owner_count: null,
  safe_threshold: null,
  is_erc4337_account: false,
  erc4337_user_operation_count: 0,
  erc4337_first_observed_block: null,
  erc4337_last_observed_block: null,
  erc4337_entrypoint_address: null,
  erc4337_entrypoint_version: null,
  erc4337_entrypoint_source: null,
  erc4337_entrypoint_deployment_block: null,
  erc4337_effective_coverage: "fixture:17000000-17006000",
  erc4337_failed_ranges: null,
  erc4337_block_chunk_size: 10_000,
  erc4337_address_batch_size: 50,
  evidence_fetch_status: "complete",
  evidence_reason_codes: "contract_code_observed|erc4337_sender_not_observed|safe_singleton_not_official",
  evidence_coverage_scope: "fixture_complete",
  evidence_coverage_start_block: 17_000_000,
  evidence_coverage_end_block: 17_006_000,
  evidence_schema_version: "account-evidence-v1",
} as const;

const eoaAccountEvidence = {
  ...contractAccountEvidence,
  account_type: "eoa_candidate",
  code_state: "no_code",
  code_size_bytes: 0,
  evidence_reason_codes: "erc4337_sender_not_observed|no_code_observed|safe_not_applicable",
  safe_verification_status: "not_applicable",
} as const;

const contractEventEvidence = {
  counterparty_account_type: "contract",
  counterparty_code_state: "contract_code",
  counterparty_code_size_bytes: 32,
  counterparty_observation_block_number: 17_006_000,
  counterparty_observation_block_timestamp: "2023-11-18T12:00:00+00:00",
  counterparty_eip7702_delegation_target: null,
  counterparty_is_safe: false,
  counterparty_safe_verification_status: "singleton_not_official",
  counterparty_safe_version: null,
  counterparty_safe_singleton_address: null,
  counterparty_safe_owner_count: null,
  counterparty_safe_threshold: null,
  counterparty_is_erc4337_account: false,
  counterparty_erc4337_user_operation_count: 0,
  counterparty_erc4337_first_observed_block: null,
  counterparty_erc4337_last_observed_block: null,
  counterparty_erc4337_entrypoint_address: null,
  counterparty_erc4337_entrypoint_version: null,
  counterparty_erc4337_entrypoint_source: null,
  counterparty_erc4337_entrypoint_deployment_block: null,
  counterparty_erc4337_effective_coverage: "fixture:17000000-17006000",
  counterparty_erc4337_failed_ranges: null,
  counterparty_erc4337_block_chunk_size: 10_000,
  counterparty_erc4337_address_batch_size: 50,
  counterparty_evidence_fetch_status: "complete",
  counterparty_evidence_reason_codes: "contract_code_observed|erc4337_sender_not_observed|safe_singleton_not_official",
  counterparty_evidence_coverage_scope: "fixture_complete",
  counterparty_evidence_coverage_start_block: 17_000_000,
  counterparty_evidence_coverage_end_block: 17_006_000,
  counterparty_evidence_schema_version: "account-evidence-v1",
} as const;

const eoaEventEvidence = {
  ...contractEventEvidence,
  counterparty_account_type: "eoa_candidate",
  counterparty_code_state: "no_code",
  counterparty_code_size_bytes: 0,
  counterparty_safe_verification_status: "not_applicable",
  counterparty_evidence_reason_codes: "erc4337_sender_not_observed|no_code_observed|safe_not_applicable",
} as const;

const graph = {
  nodes: [
    { data: { id: "wallet:0x1", label: "vitalik.eth", type: "wallet", address: "0x1", tokenAddress: null, symbol: null, accountType: null } },
    { data: { id: "token:0x2", label: "USDC", type: "token", address: null, tokenAddress: "0x2", symbol: "USDC", accountType: null } },
    { data: { id: "counterparty:0x1111111111111111111111111111111111111111", label: "0x1111...1111\ncontract", type: "counterparty", address: "0x1111111111111111111111111111111111111111", tokenAddress: null, symbol: null, accountType: "contract", isSafe: false, isErc4337Account: false } },
    { data: { id: "token:0x3", label: "SPAM", type: "token", address: null, tokenAddress: "0x3", symbol: "SPAM", accountType: null } },
    { data: { id: "counterparty:0x2222222222222222222222222222222222222222", label: "0x2222...2222\neoa_candidate", type: "counterparty", address: "0x2222222222222222222222222222222222222222", tokenAddress: null, symbol: null, accountType: "eoa_candidate", isSafe: false, isErc4337Account: false } },
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
      token_reputation: "trusted",
      token_reputation_score: 0,
      token_reputation_reasons: "curated_registry",
      transfer_count: 1,
      inbound_transfer_count: 1,
      outbound_transfer_count: 0,
      indirect_inbound_transfer_count: 1,
      indirect_outbound_transfer_count: 0,
      counterparty_count: 1,
      sender_account_count: 1,
      recipient_account_count: 0,
      amount_decimal_sum: 125,
      value_raw_sum: "125000000",
    },
    {
      wallet_id: "vitalik", wallet_address: "0x1", token_address: "0x3", token_symbol: "SPAM",
      token_name: "Spam Token", token_decimals: 18, token_status: "spam", metadata_source: "manual",
      metadata_source_url: "https://example.com/spam", token_label_reason: "Test spam",
      token_reputation: "spam", token_reputation_score: 100, token_reputation_reasons: "reviewed_spam",
      transfer_count: 1, inbound_transfer_count: 1, outbound_transfer_count: 0,
      indirect_inbound_transfer_count: 0, indirect_outbound_transfer_count: 0,
      counterparty_count: 1, sender_account_count: 1, recipient_account_count: 0,
      amount_decimal_sum: 1, value_raw_sum: "1000000000000000000",
    },
  ],
  counterparties: [
    {
      ...contractAccountEvidence,
      wallet_id: "vitalik", wallet_address: "0x1",
      counterparty_address: "0x1111111111111111111111111111111111111111",
      token_status: "trusted", transfer_count: 3,
      inbound_transfer_count: 2, outbound_transfer_count: 1, token_count: 2,
      first_seen_at: "2023-11-01T00:00:00+00:00", last_seen_at: "2023-11-14T22:15:00+00:00",
    },
    {
      ...eoaAccountEvidence,
      wallet_id: "vitalik", wallet_address: "0x1",
      counterparty_address: "0x2222222222222222222222222222222222222222",
      token_status: "spam", transfer_count: 1,
      inbound_transfer_count: 1, outbound_transfer_count: 0, token_count: 1,
      first_seen_at: "2023-11-14T22:16:00+00:00", last_seen_at: "2023-11-14T22:16:00+00:00",
    },
  ],
};

const timeline = [{ wallet_id: "vitalik", wallet_address: "0x1", block_date: "2023-11-14", token_address: "0x2", token_symbol: "USDC", token_status: "trusted", metadata_source: "manual", metadata_source_url: "https://example.com/usdc", direction: "in", transfer_count: 1, amount_decimal_sum: 125, value_raw_sum: "125000000" }];

const events = [
  {
    ...contractEventEvidence,
    transfer_id: "1-0xaaa-0",
    chain_id: 1,
    block_number: 17_000_001,
    block_timestamp: "2023-11-14T22:15:00+00:00",
    block_date: "2023-11-14",
    transaction_hash: "0xaaa",
    transaction_index: 2,
    transaction_from_address: "0x1",
    transaction_to_address: "0x2",
    log_index: 0,
    wallet_id: "vitalik",
    ens: "vitalik.eth",
    wallet_address: "0x1",
    from_address: "0x1111111111111111111111111111111111111111",
    to_address: "0x1",
    direction: "in",
    transaction_sender_relation: "transfer_recipient",
    transaction_target_relation: "token_contract",
    is_indirect: true,
    counterparty_address: "0x1111111111111111111111111111111111111111",
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
    ...eoaEventEvidence,
    transfer_id: "1-0xspam-0", chain_id: 1, block_number: 17_000_002,
    block_timestamp: "2023-11-14T22:16:00+00:00", block_date: "2023-11-14",
    transaction_hash: "0xspam", transaction_index: 3, log_index: 0, wallet_id: "vitalik",
    transaction_from_address: null, transaction_to_address: null,
    ens: "vitalik.eth", wallet_address: "0x1", direction: "in",
    from_address: "0x2222222222222222222222222222222222222222", to_address: "0x1",
    transaction_sender_relation: "unknown", transaction_target_relation: "unknown", is_indirect: null,
    counterparty_address: "0x2222222222222222222222222222222222222222", token_address: "0x3",
    token_symbol: "SPAM", token_name: "Spam Token", token_decimals: 18, token_status: "spam",
    metadata_source: "manual", metadata_source_url: "https://example.com/spam", token_label_reason: "Test spam",
    value_raw: "1000000000000000000", amount_decimal: 1,
  },
];

const dashboardEvents = [
  events[0],
  ...Array.from({ length: 10 }, (_, index) => ({
    ...events[0],
    transfer_id: `1-0xextra-${index}`,
    transaction_hash: `0xextra${index}`,
    log_index: index + 1,
  })),
  events[1],
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
  account_evidence_address_count: 2,
  account_evidence_complete_count: 2,
  safe_evidence_address_count: 0,
  erc4337_evidence_address_count: 0,
  account_evidence_observation_block_number: 17_006_000,
  account_evidence_observation_block_timestamp: "2023-11-18T12:00:00+00:00",
  account_evidence_coverage_scope: "fixture_complete",
  account_evidence_coverage_start_block: 17_000_000,
  account_evidence_coverage_end_block: 17_006_000,
  account_evidence_schema_version: "account-evidence-v1",
  token_summary_row_count: 2,
  counterparty_summary_row_count: 2,
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
  exported_counterparty_summary_count: 2,
  exported_timeline_row_count: 1,
  event_export_limit_per_status: 1000,
  graph_interaction_export_limit_per_status: 250,
  token_summary_export_limit_per_status: 500,
  counterparty_ranking_limit_per_status_combination: 50,
  timeline_row_export_limit: 5000,
  is_sampled: false,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("keeps Safe and ERC-4337 evidence independently filterable", () => {
    expect(accountMatches("safe", true, true, ["safe"])).toBe(true);
    expect(accountMatches("safe", true, true, ["erc4337_account"])).toBe(true);
    expect(accountMatches("safe", true, true, ["contract"])).toBe(false);
  });

  it("scales counterparty nodes gradually on a stable logarithmic range", () => {
    expect([1, 10, 100, 1_000, 10_000, 100_000].map(counterpartyNodeSize)).toEqual([26, 37, 47, 58, 68, 68]);
  });

  it("labels graph interactions with token and transfer count", () => {
    expect(interactionEdgeLabel("USDC", 5)).toBe("USDC x5");
    expect(interactionEdgeLabel("DAI", 12_500)).toBe("DAI x12,500");
  });

  it("aggregates token-status rows into one transfer-ranked counterparty", () => {
    const base = summaries.counterparties[0] as CounterpartySummary;
    const rows = aggregateCounterparties([
      base,
      {
        ...base,
        token_status: "unverified" as const,
        transfer_count: 2,
        inbound_transfer_count: 0,
        outbound_transfer_count: 2,
        token_count: 1,
      },
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({
      transfer_count: 5,
      inbound_transfer_count: 2,
      outbound_transfer_count: 3,
      token_count: 3,
    });
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
                : dashboardEvents;

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
    expect(screen.getAllByRole("link", { name: "0x1111...1111" })[0]).toHaveAttribute(
      "href",
      "https://etherscan.io/address/0x1111111111111111111111111111111111111111",
    );
    expect(screen.getAllByText("Contract").find((element) => element.hasAttribute("title"))).toHaveAttribute(
      "title",
      "Non-delegation contract bytecode observed at pinned block 17006000",
    );
    expect(screen.getAllByRole("link", { name: "View transaction on Etherscan" })[0]).toHaveAttribute(
      "href",
      "https://etherscan.io/tx/0xaaa",
    );
    expect(screen.getByText("Recent Events")).toBeInTheDocument();
    expect(screen.getByText("Top ERC-20 Counterparties")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "0x111...111" })).toHaveAttribute(
      "href",
      "https://etherscan.io/address/0x1111111111111111111111111111111111111111",
    );
    expect(screen.getByText("Token Flow")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Senders | Recipients" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Indirect In / Out" })).toBeInTheDocument();
    expect(screen.getAllByTitle(INDIRECT_TRANSFER_EXPLANATION).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText("in*").length).toBeGreaterThan(0);
    expect(screen.getByRole("columnheader", { name: "Amount In / Out" })).toBeInTheDocument();
    expect(screen.queryByRole("columnheader", { name: "Amount" })).not.toBeInTheDocument();
    expect(screen.queryByText("raw only")).not.toBeInTheDocument();
    expect(screen.getByText("Fixture data")).toBeInTheDocument();
    expect(screen.getByLabelText("Maximum graph interactions")).toHaveValue("25");
    expect(screen.getByText("10 of 11 events")).toBeInTheDocument();
    expect(screen.queryByLabelText("Include spam")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show less" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByText("11 of 11 events")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByText("10 of 11 events")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Status (2)"));
    const trustedStatus = screen.getByRole("checkbox", { name: "trusted" });
    const unverifiedStatus = screen.getByRole("checkbox", { name: "unverified" });
    const suspectedStatus = screen.getByRole("checkbox", { name: "suspected spam" });
    const spamStatus = screen.getByRole("checkbox", { name: "spam" });
    expect(trustedStatus).toBeChecked();
    expect(unverifiedStatus).toBeChecked();
    expect(suspectedStatus).toBeEnabled();
    expect(suspectedStatus).not.toBeChecked();
    expect(spamStatus).toBeEnabled();
    expect(spamStatus).not.toBeChecked();
    fireEvent.click(trustedStatus);
    expect(screen.queryByText("USDC")).not.toBeInTheDocument();
    fireEvent.click(trustedStatus);
    expect(screen.queryByText("SPAM")).not.toBeInTheDocument();
    fireEvent.click(spamStatus);
    expect(spamStatus).toBeChecked();
    expect(screen.getAllByText("SPAM").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByText("Account evidence (6)"));
    const contractAccount = screen.getByRole("checkbox", { name: "Contract" });
    const eoaCandidate = screen.getByRole("checkbox", { name: "EOA candidate" });
    expect(contractAccount).toBeChecked();
    expect(eoaCandidate).toBeChecked();
    fireEvent.click(contractAccount);
    expect(screen.queryByRole("link", { name: "0x111...111" })).not.toBeInTheDocument();
    fireEvent.click(contractAccount);

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "contract" } });
    expect(screen.getAllByRole("link", { name: "0x1111...1111" }).length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "0x1111" } });
    expect(screen.getAllByText("0x1111...1111").length).toBeGreaterThan(0);

    fireEvent.change(screen.getByLabelText("Filter dashboard"), { target: { value: "0xaaa" } });
    expect(screen.getByText("2 nodes / 1 edges")).toBeInTheDocument();

    const graphElement = screen.getByRole("img", { name: /wallet interaction graph/i });
    const graphShell = graphElement.parentElement;
    expect(graphShell).toHaveAttribute("data-graph-theme", "light");

    fireEvent.click(screen.getByLabelText("Open graph theater mode"));
    expect(screen.getByRole("dialog", { name: "Interaction Graph theater mode" })).toHaveClass("theater");
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByLabelText("Exit graph theater mode")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Interaction Graph theater mode" })).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");

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
