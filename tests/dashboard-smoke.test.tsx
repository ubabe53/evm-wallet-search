import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  App,
  accountEvidenceCoverageDescription,
  accountEvidenceCoverageLabel,
  accountEvidenceObservationBlockLabel,
  accountEvidenceObservationTimeLabel,
  accountMatches,
  aggregateCounterparties,
  aggregateTimelineRows,
  aggregateTokenSummaries,
  buildCounterpartyGraph,
  counterpartyNodeSize,
  etherscanAddressUrl,
  etherscanInteractionUrl,
  etherscanTokenUrl,
  etherscanTransactionUrl,
  graphStyles,
  interactionEdgeLabel,
  snapshotCoverageLabel,
  INDIRECT_TRANSFER_EXPLANATION,
} from "../src/App";
import type { CounterpartySummary, DashboardGraph, TimelineRow, TokenSummary } from "../src/data";

const contractAccountEvidence = {
  account_type: "contract",
  code_state: "contract_code",
  code_size_bytes: 32,
  observation_block_number: 22_500_000,
  observation_block_timestamp: "2025-05-17T03:11:47+00:00",
  eip7702_delegation_target: null,
  evidence_fetch_status: "complete",
  evidence_reason_codes: "contract_code_observed",
  evidence_schema_version: "account-evidence-v2",
} as const;

const eoaAccountEvidence = {
  ...contractAccountEvidence,
  account_type: "eoa_candidate",
  code_state: "no_code",
  code_size_bytes: 0,
  evidence_reason_codes: "no_code_observed",
} as const;

const contractEventEvidence = {
  counterparty_account_type: "contract",
  counterparty_code_state: "contract_code",
  counterparty_code_size_bytes: 32,
  counterparty_observation_block_number: 22_500_000,
  counterparty_observation_block_timestamp: "2025-05-17T03:11:47+00:00",
  counterparty_eip7702_delegation_target: null,
  counterparty_evidence_fetch_status: "complete",
  counterparty_evidence_reason_codes: "contract_code_observed",
  counterparty_evidence_schema_version: "account-evidence-v2",
} as const;

const eoaEventEvidence = {
  ...contractEventEvidence,
  counterparty_account_type: "eoa_candidate",
  counterparty_code_state: "no_code",
  counterparty_code_size_bytes: 0,
  counterparty_evidence_reason_codes: "no_code_observed",
} as const;

const highQualityGraph = {
  recognitionStatus: "recognized",
  recognitionSource: "registry",
  recognitionOverrideStatus: null,
  metadataAvailability: "complete",
  tokenQuality: "high_confidence",
  tokenQualitySources: ["trustwallet", "uniswap", "coingecko"],
  tokenQualitySourceCount: 3,
  tokenQualityReason: "reviewed_manual_approval",
  tokenQualityProvenance: "https://example.com/usdc",
  tokenQualityVersion: "token-quality-v1",
  tokenReputationVersion: "token-reputation-v2",
  counterpartyAccountType: "contract",
} as const;

const unknownQualityGraph = {
  recognitionStatus: "other",
  recognitionSource: "automatic",
  recognitionOverrideStatus: null,
  metadataAvailability: "complete",
  tokenQuality: "unknown",
  tokenQualitySources: [],
  tokenQualitySourceCount: 0,
  tokenQualityReason: "no_registry_or_reviewed_approval",
  tokenQualityProvenance: "https://example.com/spam",
  tokenQualityVersion: "token-quality-v1",
  tokenReputationVersion: "token-reputation-v2",
  counterpartyAccountType: "eoa_candidate",
} as const;

const highQuality = {
  recognition_status: "recognized",
  recognition_reason: "registry_match",
  recognition_source: "registry",
  recognition_version: "token-recognition-v1",
  recognition_override_status: null,
  metadata_availability: "complete",
  token_quality: "high_confidence",
  token_quality_sources: ["trustwallet", "uniswap", "coingecko"],
  token_quality_source_count: 3,
  token_quality_reason: "reviewed_manual_approval",
  token_quality_provenance: "https://example.com/usdc",
  token_quality_version: "token-quality-v1",
  token_reputation_version: "token-reputation-v2",
  counterparty_account_type: "contract",
} as const;

const unknownQuality = {
  recognition_status: "other",
  recognition_reason: "no_registry_match",
  recognition_source: "automatic",
  recognition_version: "token-recognition-v1",
  recognition_override_status: null,
  metadata_availability: "complete",
  token_quality: "unknown",
  token_quality_sources: [],
  token_quality_source_count: 0,
  token_quality_reason: "no_registry_or_reviewed_approval",
  token_quality_provenance: "https://example.com/spam",
  token_quality_version: "token-quality-v1",
  token_reputation_version: "token-reputation-v2",
  counterparty_account_type: "eoa_candidate",
} as const;

const graph = {
  nodes: [
    { data: { id: "wallet:0x1", label: "vitalik.eth", type: "wallet", address: "0x1", tokenAddress: null, symbol: null, accountType: null } },
    { data: { id: "token:0x2", label: "USDC", type: "token", address: null, tokenAddress: "0x2", symbol: "USDC", accountType: null } },
    { data: { id: "counterparty:0x1111111111111111111111111111111111111111", label: "0x1111...1111\nContract", type: "counterparty", address: "0x1111111111111111111111111111111111111111", tokenAddress: null, symbol: null, accountType: "contract" } },
    { data: { id: "token:0x3", label: "SPAM", type: "token", address: null, tokenAddress: "0x3", symbol: "SPAM", accountType: null } },
    { data: { id: "counterparty:0x2222222222222222222222222222222222222222", label: "0x2222...2222\nEOA", type: "counterparty", address: "0x2222222222222222222222222222222222222222", tokenAddress: null, symbol: null, accountType: "eoa_candidate" } },
  ],
  edges: [
    { data: { ...highQualityGraph, id: "edge:1", interactionId: "interaction:0x1:0x1111111111111111111111111111111111111111:0x2:in", edgeRole: "token_counterparty", source: "counterparty:0x1111111111111111111111111111111111111111", target: "token:0x2", walletAddress: "0x1", counterpartyAddress: "0x1111111111111111111111111111111111111111", direction: "in", tokenAddress: "0x2", tokenSymbol: "USDC", tokenStatus: "trusted", metadataSource: "manual", metadataSourceUrl: "https://example.com/usdc", transferCount: 1, counterpartyTransferCount: 1 } },
    { data: { ...highQualityGraph, id: "edge:2", interactionId: "interaction:0x1:0x1111111111111111111111111111111111111111:0x2:in", edgeRole: "wallet_token", source: "token:0x2", target: "wallet:0x1", walletAddress: "0x1", counterpartyAddress: "0x1111111111111111111111111111111111111111", direction: "in", tokenAddress: "0x2", tokenSymbol: "USDC", tokenStatus: "trusted", metadataSource: "manual", metadataSourceUrl: "https://example.com/usdc", transferCount: 1, counterpartyTransferCount: 1 } },
    { data: { ...unknownQualityGraph, id: "edge:3", interactionId: "interaction:0x1:0x2222222222222222222222222222222222222222:0x3:in", edgeRole: "token_counterparty", source: "counterparty:0x2222222222222222222222222222222222222222", target: "token:0x3", walletAddress: "0x1", counterpartyAddress: "0x2222222222222222222222222222222222222222", direction: "in", tokenAddress: "0x3", tokenSymbol: "SPAM", tokenStatus: "spam", metadataSource: "manual", metadataSourceUrl: "https://example.com/spam", transferCount: 1, counterpartyTransferCount: 1 } },
    { data: { ...unknownQualityGraph, id: "edge:4", interactionId: "interaction:0x1:0x2222222222222222222222222222222222222222:0x3:in", edgeRole: "wallet_token", source: "token:0x3", target: "wallet:0x1", walletAddress: "0x1", counterpartyAddress: "0x2222222222222222222222222222222222222222", direction: "in", tokenAddress: "0x3", tokenSymbol: "SPAM", tokenStatus: "spam", metadataSource: "manual", metadataSourceUrl: "https://example.com/spam", transferCount: 1, counterpartyTransferCount: 1 } },
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
      ...highQuality,
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
      value_raw_sum: "125000000",
    },
    {
      wallet_id: "vitalik", wallet_address: "0x1", token_address: "0x3", token_symbol: "SPAM",
      token_name: "Spam Token", token_decimals: 18, token_status: "spam", metadata_source: "manual",
      metadata_source_url: "https://example.com/spam", token_label_reason: "Test spam",
      ...unknownQuality,
      token_reputation: "spam", token_reputation_score: 100, token_reputation_reasons: "reviewed_spam",
      transfer_count: 1, inbound_transfer_count: 1, outbound_transfer_count: 0,
      indirect_inbound_transfer_count: 0, indirect_outbound_transfer_count: 0,
      counterparty_count: 1, sender_account_count: 1, recipient_account_count: 0,
      value_raw_sum: "1000000000000000000",
    },
  ],
  counterparties: [
    {
      ...contractAccountEvidence,
      wallet_id: "vitalik", wallet_address: "0x1",
      counterparty_address: "0x1111111111111111111111111111111111111111",
      token_status: "trusted", recognition_status: "recognized", token_quality: "high_confidence", transfer_count: 3,
      inbound_transfer_count: 2, outbound_transfer_count: 1, token_count: 2,
      first_seen_at: "2023-11-01T00:00:00+00:00", last_seen_at: "2023-11-14T22:15:00+00:00",
    },
    {
      ...eoaAccountEvidence,
      wallet_id: "vitalik", wallet_address: "0x1",
      counterparty_address: "0x2222222222222222222222222222222222222222",
      token_status: "spam", recognition_status: "other", token_quality: "unknown", transfer_count: 1,
      inbound_transfer_count: 1, outbound_transfer_count: 0, token_count: 1,
      first_seen_at: "2023-11-14T22:16:00+00:00", last_seen_at: "2023-11-14T22:16:00+00:00",
    },
  ],
};

const timeline = [{ ...highQuality, wallet_id: "vitalik", wallet_address: "0x1", block_date: "2023-11-14", token_address: "0x2", token_symbol: "USDC", token_status: "trusted", metadata_source: "manual", metadata_source_url: "https://example.com/usdc", direction: "in", transfer_count: 1, value_raw_sum: "125000000" }];

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
    ...highQuality,
    value_raw: "125000000",
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
    ...unknownQuality,
    value_raw: "1000000000000000000",
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
  snapshot_run_id: null,
  snapshot_start_block: null,
  snapshot_increment_start_block: null,
  snapshot_end_block: null,
  snapshot_end_block_hash: null,
  snapshot_finality_policy: null,
  snapshot_scope_version: null,
  transfer_count: 2,
  token_count: 2,
  recognized_transfer_count: 1,
  recognized_token_count: 1,
  other_transfer_count: 1,
  other_token_count: 1,
  counterparty_count: 2,
  non_spam_transfer_count: 1,
  non_spam_token_count: 1,
  non_spam_counterparty_count: 1,
  spam_transfer_count: 1,
  spam_token_count: 1,
  interaction_count: 2,
  account_evidence_population_scope: "distinct_nonzero_nonself_event_counterparties",
  account_evidence_eligible_address_count: 3,
  account_evidence_classified_address_count: 2,
  account_evidence_failed_address_count: 0,
  account_evidence_not_checked_address_count: 1,
  account_evidence_address_coverage_rate: 2 / 3,
  account_evidence_eligible_event_count: 4,
  account_evidence_classified_event_count: 3,
  account_evidence_failed_event_count: 0,
  account_evidence_not_checked_event_count: 1,
  account_evidence_event_coverage_rate: 0.75,
  account_evidence_observation_block_number_min: 22_500_000,
  account_evidence_observation_block_number_max: 22_500_000,
  account_evidence_observation_block_timestamp_min: "2025-05-17T03:11:47+00:00",
  account_evidence_observation_block_timestamp_max: "2025-05-17T03:11:47+00:00",
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
  quality_counts: {
    high_confidence: { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    listed: { transfer_count: 0, token_count: 0, counterparty_count: 0 },
    unknown: { transfer_count: 1, token_count: 1, counterparty_count: 1 },
  },
  status_quality_counts: {
    "trusted+unverified|high_confidence": { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "trusted|high_confidence": { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "unverified|high_confidence": { transfer_count: 0, token_count: 0, counterparty_count: 0 },
    "trusted+unverified+spam|high_confidence": { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "trusted+unverified+spam|high_confidence+unknown": { transfer_count: 2, token_count: 2, counterparty_count: 2 },
  },
  status_quality_account_counts: {
    "trusted+unverified|high_confidence+listed+unknown|eoa_candidate+contract": {
      transfer_count: 1,
      token_count: 1,
      counterparty_count: 1,
    },
    "trusted+unverified+suspected_spam+spam|high_confidence+listed+unknown|eoa_candidate+contract": {
      transfer_count: 2,
      token_count: 2,
      counterparty_count: 2,
    },
  },
  exported_event_count: 2,
  exported_interaction_count: 2,
  exported_token_summary_count: 2,
  exported_counterparty_summary_count: 2,
  exported_timeline_row_count: 1,
  status_quality_account_evidence_cell_count: 2,
  event_export_limit_per_status_quality_account_evidence: 1000,
  graph_interaction_export_limit_per_status_quality_account_evidence: 250,
  token_summary_ranking_limit_per_status_quality_account_selection: 500,
  token_summary_ranking_selection_count: 315,
  token_summary_ranking_candidate_token_count: 2,
  token_summary_rankings_exact_for_all_filter_selections: true,
  counterparty_ranking_limit_per_status_quality_account_selection: 50,
  counterparty_token_status_combination_count: 15,
  counterparty_token_quality_combination_count: 7,
  counterparty_account_filter_combination_count: 3,
  counterparty_ranking_selection_count: 315,
  counterparty_ranking_candidate_address_count: 2,
  counterparty_rankings_exact_for_all_filter_selections: true,
  timeline_row_export_limit_per_status_quality_account_evidence: 5000,
  is_sampled: false,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe("App", () => {
  it("exposes binary account filters while retaining unresolved rows in the all selection", () => {
    expect(accountMatches("eoa_candidate", ["eoa_candidate"])).toBe(true);
    expect(accountMatches("contract", ["eoa_candidate"])).toBe(false);
    expect(accountMatches("unknown", ["eoa_candidate", "contract"])).toBe(true);
  });

  it("renders single and mixed address-type observation ranges", () => {
    expect(accountEvidenceObservationBlockLabel(22_500_000, 22_500_000)).toBe("block 22,500,000");
    expect(accountEvidenceObservationBlockLabel(22_500_000, 22_600_000)).toBe("blocks 22,500,000–22,600,000");
    expect(accountEvidenceObservationTimeLabel("2025-05-17T03:11:47+00:00", "2025-05-17T03:11:47+00:00"))
      .toBe("2025-05-17T03:11:47+00:00");
    expect(accountEvidenceObservationTimeLabel("2025-05-17T03:11:47+00:00", "2025-05-18T03:11:47+00:00"))
      .toBe("2025-05-17T03:11:47+00:00–2025-05-18T03:11:47+00:00");
  });

  it("shows account coverage with explicit address and event denominators", () => {
    expect(accountEvidenceCoverageLabel(metadata)).toBe("address types 2/3");
    expect(accountEvidenceCoverageDescription(metadata)).toContain(
      "2 of 3 nonzero, nonself counterparties classified (66.7%)",
    );
    expect(accountEvidenceCoverageDescription(metadata)).toContain(
      "3 of 4 captured transfers have classified counterparties (75%)",
    );
    expect(accountEvidenceCoverageDescription(metadata)).toContain("0 failed; 1 not checked");
  });

  it("labels only verified finalized snapshot coverage", () => {
    expect(snapshotCoverageLabel({
      snapshot_start_block: 3,
      snapshot_end_block: 25_523_374,
      snapshot_finality_policy: "ethereum_finalized",
    })).toBe("Blocks 3–25,523,374 · Finalized");
    expect(snapshotCoverageLabel({
      snapshot_start_block: null,
      snapshot_end_block: null,
      snapshot_finality_policy: null,
    })).toBe("Coverage not recorded");
  });

  it("does not expose removed Safe or ERC-4337 graph channels", () => {
    const styles = graphStyles(document.createElement("div"));
    const selectors = styles.map((rule) => rule.selector);
    expect(selectors).not.toContain("node[?isSafe]");
    expect(selectors).not.toContain("node[?isErc4337Account]");
    expect(selectors).not.toContain('node[accountType = "eip7702_delegated"]');
    const unknownStyle = styles.find((rule) => rule.selector === 'node[accountType = "unknown"]') as { style?: object };
    const edgeStyle = styles.find((rule) => rule.selector === "edge") as { style?: object };
    expect(unknownStyle.style)
      .toMatchObject({ "border-style": "solid" });
    expect(edgeStyle.style)
      .toMatchObject({ "curve-style": "straight", "target-arrow-shape": "none" });
  });

  it("scales counterparty nodes gradually on a stable logarithmic range", () => {
    expect([1, 10, 100, 1_000, 10_000, 100_000].map(counterpartyNodeSize)).toEqual([26, 37, 47, 58, 68, 68]);
  });

  it("labels graph edges with captured transfer counts", () => {
    expect(interactionEdgeLabel(1)).toBe("1 transfer");
    expect(interactionEdgeLabel(12_500)).toBe("12,500 transfers");
  });

  it("uses the same mixed-recognition aggregate for graph and counterparty ranking", () => {
    const base = summaries.counterparties[0] as unknown as CounterpartySummary;
    const counterpartyRows = [
      base,
      {
        ...base,
        token_status: "unverified" as const,
        recognition_status: "other" as const,
        token_quality: "listed" as const,
        transfer_count: 2,
        inbound_transfer_count: 0,
        outbound_transfer_count: 2,
        token_count: 1,
      },
    ];
    const projected = buildCounterpartyGraph({
      graph: {
        ...graph,
        edges: graph.edges.map((edge) => ({
          data: { ...edge.data, counterpartyTransferCount: 99 },
        })) as unknown as DashboardGraph["edges"],
      } as unknown as DashboardGraph,
      summaries: { counterparties: counterpartyRows },
    }, 25);

    expect(aggregateCounterparties(counterpartyRows)[0].transfer_count).toBe(5);
    expect(projected.edges).toHaveLength(1);
    expect(projected.edges[0].data).toMatchObject({
      counterpartyAddress: base.counterparty_address,
      transferCount: 5,
      counterpartyTransferCount: 5,
      label: "5 transfers",
    });
  });

  it("preserves counterparty recency as the graph tie-breaker", () => {
    const older = {
      ...(summaries.counterparties[0] as unknown as CounterpartySummary),
      transfer_count: 5,
      last_seen_at: "2024-01-01T00:00:00+00:00",
    };
    const newer = {
      ...(summaries.counterparties[1] as unknown as CounterpartySummary),
      transfer_count: 5,
      last_seen_at: "2024-02-01T00:00:00+00:00",
    };
    const projected = buildCounterpartyGraph({
      graph: graph as unknown as DashboardGraph,
      summaries: { counterparties: [older, newer] },
    }, 2);

    expect(projected.edges.map((edge) => edge.data.counterpartyAddress)).toEqual([
      newer.counterparty_address,
      older.counterparty_address,
    ]);
  });

  it("aggregates token classification rows into one transfer-ranked counterparty", () => {
    const base = summaries.counterparties[0] as unknown as CounterpartySummary;
    const rows = aggregateCounterparties([
      base,
      {
        ...base,
        token_status: "unverified" as const,
        recognition_status: "other" as const,
        token_quality: "listed" as const,
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

  it("aggregates matching account cells back to token grain before ranking", () => {
    const base = summaries.tokens[0] as unknown as TokenSummary;
    const rows = aggregateTokenSummaries([
      { ...base, counterparty_account_type: "contract", transfer_count: 60, value_raw_sum: "60" },
      {
        ...base,
        counterparty_account_type: "eoa_candidate",
        transfer_count: 60,
        value_raw_sum: "60",
      },
      {
        ...base,
        token_address: "0xbbb",
        token_symbol: "BBB",
        counterparty_account_type: "contract",
        transfer_count: 100,
        value_raw_sum: "100",
      },
    ]);

    expect(rows.map((row) => [row.token_address, row.transfer_count])).toEqual([
      ["0x2", 120],
      ["0xbbb", 100],
    ]);
    expect(rows[0].value_raw_sum).toBe("120");
  });

  it("aggregates account cells back to the displayed daily token-direction grain", () => {
    const base = timeline[0] as unknown as TimelineRow;
    const rows = aggregateTimelineRows([
      { ...base, counterparty_account_type: "contract", transfer_count: 2, value_raw_sum: "10" },
      {
        ...base,
        counterparty_account_type: "eoa_candidate",
        transfer_count: 3,
        value_raw_sum: "20",
      },
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ transfer_count: 5, value_raw_sum: "30" });
  });

  it("builds canonical Etherscan routes", () => {
    expect(etherscanAddressUrl("0xabc")).toBe("https://etherscan.io/address/0xabc");
    expect(etherscanTokenUrl("0xdef")).toBe("https://etherscan.io/token/0xdef");
    expect(etherscanTransactionUrl("0x123")).toBe("https://etherscan.io/tx/0x123");
    const interaction = new URL(etherscanInteractionUrl("0xwallet", "0xcounterparty"));
    expect(interaction.pathname).toBe("/advanced-filter");
    expect(interaction.searchParams.get("txntype")).toBe("2");
    expect(interaction.searchParams.getAll("fadd")).toEqual(["0xwallet", "0xcounterparty"]);
    expect(interaction.searchParams.getAll("tadd")).toEqual(["0xwallet", "0xcounterparty"]);
    expect(interaction.searchParams.get("qt")).toBe("1");
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
      "Contract bytecode observed at pinned block 22500000",
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
    expect(screen.getByText("Data snapshot").parentElement).toHaveTextContent(
      "Data snapshotCoverage not recorded",
    );
    expect(screen.getByLabelText("Maximum graph counterparties")).toHaveValue("25");
    expect(screen.getByText("10 of 12 events")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "All" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Recognized" })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: "Other" })).not.toBeChecked();
    expect(screen.queryByText("Status (2)")).not.toBeInTheDocument();
    expect(screen.queryByText("Quality (1)")).not.toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Recognition" })).toBeInTheDocument();
    expect(screen.queryByText(/^trusted$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^high confidence$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show less" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show more" }));
    expect(screen.getByText("12 of 12 events")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show less" }));
    expect(screen.getByText("10 of 12 events")).toBeInTheDocument();
    expect(screen.getAllByText("SPAM").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("radio", { name: "Recognized" }));
    expect(screen.queryByText("SPAM")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "Other" }));
    expect(screen.getAllByText("SPAM").length).toBeGreaterThan(0);
    expect(screen.queryByText("USDC")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "All" }));
    expect(screen.getAllByText("USDC").length).toBeGreaterThan(0);

    fireEvent.mouseEnter(screen.getByLabelText("What recognized means"));
    expect(screen.getByText(/exact Ethereum contract address appears in Uniswap/)).toBeInTheDocument();
    expect(screen.getByRole("tooltip", { name: /Recognized tokens/ })).toBeInTheDocument();
    expect(screen.getByLabelText("How token recognition works")).toBeInTheDocument();
    expect(screen.getAllByRole("combobox", { name: /Recognition for/ }).every((control) => control.hasAttribute("disabled"))).toBe(true);

    fireEvent.mouseEnter(screen.getByLabelText("How address type works"));
    expect(screen.getByRole("tooltip", { name: /Address type/ })).toBeInTheDocument();
    fireEvent.click(screen.getByText("Address type (2)"));
    const contractAccount = screen.getByRole("checkbox", { name: "Contract" });
    const eoaCandidate = screen.getByRole("checkbox", { name: "EOA" });
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

    const graphElement = screen.getByRole("img", { name: /wallet counterparty graph/i });
    const graphShell = graphElement.parentElement;
    expect(graphShell).toHaveAttribute("data-graph-theme", "light");

    fireEvent.click(screen.getByLabelText("Open graph theater mode"));
    expect(screen.getByRole("dialog", { name: "Counterparty Graph theater mode" })).toHaveClass("theater");
    expect(document.body.style.overflow).toBe("hidden");
    expect(screen.getByLabelText("Exit graph theater mode")).toBeInTheDocument();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Counterparty Graph theater mode" })).not.toBeInTheDocument();
    expect(document.body.style.overflow).toBe("");

    fireEvent.click(screen.getByLabelText("Switch to dark theme"));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(graphElement).toBe(screen.getByRole("img", { name: /wallet counterparty graph/i }));
    expect(graphShell).toHaveAttribute("data-graph-theme", "dark");

    fireEvent.click(screen.getByLabelText("Switch to light theme"));
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(graphElement).toBe(screen.getByRole("img", { name: /wallet counterparty graph/i }));
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
