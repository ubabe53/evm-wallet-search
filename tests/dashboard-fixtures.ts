const contractAccountEvidence = {
  account_type: "contract",
  code_state: "contract_code",
  observation_block_number: 22_500_000,
  eip7702_delegation_target: null,
} as const;

const eoaAccountEvidence = {
  ...contractAccountEvidence,
  account_type: "eoa_candidate",
  code_state: "no_code",
} as const;

const contractEventEvidence = {
  counterparty_account_type: "contract",
  counterparty_code_state: "contract_code",
  counterparty_observation_block_number: 22_500_000,
  counterparty_eip7702_delegation_target: null,
} as const;

const eoaEventEvidence = {
  ...contractEventEvidence,
  counterparty_account_type: "eoa_candidate",
  counterparty_code_state: "no_code",
} as const;

const recognizedEvidence = {
  recognition_status: "recognized",
  recognition_override_status: null,
  counterparty_account_type: "contract",
} as const;

const otherEvidence = {
  recognition_status: "other",
  recognition_override_status: null,
  counterparty_account_type: "eoa_candidate",
} as const;

export const summaries = {
  tokens: [
    {
      chain_id: 1,
      wallet_address: "0x1",
      token_address: "0x2",
      token_symbol: "USDC",
      token_name: "USD Coin",
      ...recognizedEvidence,
      transfer_count: 1,
      inbound_transfer_count: 1,
      outbound_transfer_count: 0,
      self_transfer_count: 0,
      indirect_inbound_transfer_count: 1,
      indirect_outbound_transfer_count: 0,
      counterparty_count: 1,
      sender_account_count: 1,
      recipient_account_count: 0,
    },
    {
      chain_id: 1, wallet_address: "0x1", token_address: "0x3", token_symbol: "OTHER",
      token_name: "Other Token",
      ...otherEvidence,
      transfer_count: 1, inbound_transfer_count: 1, outbound_transfer_count: 0,
      self_transfer_count: 0,
      indirect_inbound_transfer_count: 0, indirect_outbound_transfer_count: 0,
      counterparty_count: 1, sender_account_count: 1, recipient_account_count: 0,
    },
  ],
  counterparties: [
    {
      ...contractAccountEvidence,
      chain_id: 1, wallet_address: "0x1",
      counterparty_address: "0x1111111111111111111111111111111111111111",
      recognition_status: "recognized", transfer_count: 3,
      inbound_transfer_count: 2, outbound_transfer_count: 1, token_count: 2,
      first_seen_at: "2023-11-01T00:00:00+00:00", last_seen_at: "2023-11-14T22:15:00+00:00",
    },
    {
      ...eoaAccountEvidence,
      chain_id: 1, wallet_address: "0x1",
      counterparty_address: "0x2222222222222222222222222222222222222222",
      recognition_status: "other", transfer_count: 1,
      inbound_transfer_count: 1, outbound_transfer_count: 0, token_count: 1,
      first_seen_at: "2023-11-14T22:16:00+00:00", last_seen_at: "2023-11-14T22:16:00+00:00",
    },
  ],
};

export const timeline = [{ ...recognizedEvidence, chain_id: 1, wallet_address: "0x1", block_date: "2023-11-14", token_address: "0x2", token_symbol: "USDC", direction: "in", transfer_count: 1 }];

const events = [
  {
    ...contractEventEvidence,
    transfer_id: "1-0xaaa-0",
    chain_id: 1,
    wallet_address: "0x1",
    block_number: 17_000_001,
    block_timestamp: "2023-11-14T22:15:00+00:00",
    transaction_hash: "0xaaa",
    transaction_index: 2,
    log_index: 0,
    direction: "in",
    is_indirect: true,
    counterparty_address: "0x1111111111111111111111111111111111111111",
    token_address: "0x2",
    token_symbol: "USDC",
    token_name: "USD Coin",
    ...recognizedEvidence,
  },
  {
    ...eoaEventEvidence,
    transfer_id: "1-0xother-0", chain_id: 1, block_number: 17_000_002,
    block_timestamp: "2023-11-14T22:16:00+00:00",
    transaction_hash: "0xother", transaction_index: 3, log_index: 0,
    wallet_address: "0x1", direction: "in",
    is_indirect: null,
    counterparty_address: "0x2222222222222222222222222222222222222222", token_address: "0x3",
    token_symbol: "OTHER", token_name: "Other Token",
    ...otherEvidence,
  },
];

export const dashboardEvents = [
  events[0],
  ...Array.from({ length: 10 }, (_, index) => ({
    ...events[0],
    transfer_id: `1-0xextra-${index}`,
    transaction_hash: `0xextra${index}`,
    log_index: index + 1,
    ...(index === 8 ? {
      transfer_id: "1-0xself-0",
      transaction_hash: "0xself",
      direction: "self",
      is_indirect: false,
      counterparty_address: "0x1",
    } : {}),
  })),
  events[1],
];

export const metadata = {
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
  recognition_counts: {
    recognized: { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    other: { transfer_count: 1, token_count: 1, counterparty_count: 1 },
    "recognized+other": { transfer_count: 2, token_count: 2, counterparty_count: 2 },
  },
  recognition_account_counts: {
    "recognized|eoa_candidate+contract": {
      transfer_count: 1,
      token_count: 1,
      counterparty_count: 1,
    },
    "recognized+other|eoa_candidate+contract": {
      transfer_count: 2,
      token_count: 2,
      counterparty_count: 2,
    },
  },
  exported_event_count: 2,
  exported_token_summary_count: 2,
  exported_counterparty_summary_count: 2,
  exported_timeline_row_count: 1,
  recognition_account_evidence_cell_count: 2,
  event_export_limit_per_recognition_account_evidence: 1000,
  token_summary_ranking_limit_per_recognition_account_selection: 500,
  token_summary_ranking_selection_count: 9,
  token_summary_ranking_candidate_token_count: 2,
  token_summary_rankings_exact_for_all_filter_selections: true,
  counterparty_ranking_limit_per_recognition_account_selection: 50,
  counterparty_recognition_combination_count: 3,
  counterparty_account_filter_combination_count: 3,
  counterparty_ranking_selection_count: 9,
  counterparty_ranking_candidate_address_count: 2,
  counterparty_rankings_exact_for_all_filter_selections: true,
  timeline_row_export_limit_per_recognition_account_evidence: 5000,
  is_sampled: false,
};
