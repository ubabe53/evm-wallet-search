export type GraphNode = {
  data: {
    id: string;
    label: string;
    type: "wallet" | "counterparty" | "token";
    address: string | null;
    tokenAddress: string | null;
    symbol: string | null;
    accountType: AccountType | null;
    codeState: CodeState | null;
    observationBlockNumber: number | null;
    observationBlockTimestamp: string | null;
    eip7702DelegationTarget: string | null;
    isSafe: boolean | null;
    safeVerificationStatus: SafeVerificationStatus | null;
    safeVersion: string | null;
    safeSingletonAddress: string | null;
    safeOwnerCount: number | null;
    safeThreshold: number | null;
    isErc4337Account: boolean | null;
    erc4337EntrypointAddress: string | null;
    erc4337EntrypointVersion: string | null;
    erc4337EntrypointSource: string | null;
    erc4337EntrypointDeploymentBlock: string | null;
    erc4337EffectiveCoverage: string | null;
    erc4337FailedRanges: string | null;
    evidenceFetchStatus: EvidenceFetchStatus | null;
    evidenceReasonCodes: string | null;
    evidenceCoverageStartBlock: number | null;
    evidenceCoverageEndBlock: number | null;
    size?: number;
    transferCount?: number;
  };
};

export type GraphEdge = {
  data: {
    id: string;
    interactionId: string;
    edgeRole: "wallet_token" | "token_counterparty" | "wallet_counterparty";
    source: string;
    target: string;
    walletAddress: string;
    counterpartyAddress: string;
    direction: "in" | "out";
    tokenAddress: string;
    tokenSymbol: string;
    label?: string;
    tokenStatus: TokenStatus;
    metadataSource: string | null;
    metadataSourceUrl: string | null;
    tokenReputation: TokenReputation;
    tokenReputationScore: number;
    tokenReputationReasons: string;
    interactionLegitimacy: InteractionLegitimacy;
    interactionLegitimacyScore: number;
    interactionLegitimacyReasons: string;
    transferCount: number;
    counterpartyTransferCount: number;
    amountDecimalSum: number | null;
  };
};

export type TokenStatus = "trusted" | "unverified" | "suspected_spam" | "spam";
export type TokenReputation = TokenStatus;
export type InteractionLegitimacy = "not_suspicious" | "uncertain" | "suspicious";
export type TransactionSenderRelation = "transfer_sender" | "transfer_recipient" | "other" | "unknown";
export type TransactionTargetRelation = "token_contract" | "transfer_sender" | "transfer_recipient" | "other" | "unknown";
export type AccountType = "eoa_candidate" | "eip7702_delegated" | "safe" | "erc4337_account" | "contract" | "unknown";
export type AccountFilter = AccountType;
export type CodeState = "no_code" | "eip7702_delegated" | "contract_code" | "unknown";
export type SafeVerificationStatus = "verified" | "singleton_not_official" | "calls_inconsistent" | "evidence_unavailable" | "not_applicable" | "not_checked";
export type EvidenceFetchStatus = "complete" | "partial" | "failed" | "not_fetched";

export type AccountEvidence = {
  account_type: AccountType;
  code_state: CodeState;
  code_size_bytes: number | null;
  observation_block_number: number | null;
  observation_block_timestamp: string | null;
  eip7702_delegation_target: string | null;
  is_safe: boolean;
  safe_verification_status: SafeVerificationStatus;
  safe_version: string | null;
  safe_singleton_address: string | null;
  safe_owner_count: number | null;
  safe_threshold: number | null;
  is_erc4337_account: boolean;
  erc4337_user_operation_count: number | null;
  erc4337_first_observed_block: number | null;
  erc4337_last_observed_block: number | null;
  erc4337_entrypoint_address: string | null;
  erc4337_entrypoint_version: string | null;
  erc4337_entrypoint_source: string | null;
  erc4337_entrypoint_deployment_block: string | null;
  erc4337_effective_coverage: string | null;
  erc4337_failed_ranges: string | null;
  erc4337_block_chunk_size: number | null;
  erc4337_address_batch_size: number | null;
  evidence_fetch_status: EvidenceFetchStatus;
  evidence_reason_codes: string;
  evidence_coverage_scope: string | null;
  evidence_coverage_start_block: number | null;
  evidence_coverage_end_block: number | null;
  evidence_schema_version: string | null;
};

export type ClassificationEvidence = {
  token_reputation: TokenReputation;
  token_reputation_score: number;
  token_reputation_reasons: string;
  interaction_legitimacy: InteractionLegitimacy;
  interaction_legitimacy_score: number;
  interaction_legitimacy_reasons: string;
};

export type DashboardGraph = {
  nodes: GraphNode[];
  edges: GraphEdge[];
};

export type TokenSummary = {
  wallet_id: string;
  wallet_address: string;
  token_address: string;
  token_symbol: string;
  token_name: string | null;
  token_decimals: number | null;
  token_status: TokenStatus;
  metadata_source: string | null;
  metadata_source_url: string | null;
  token_label_reason: string | null;
  token_reputation: TokenReputation;
  token_reputation_score: number;
  token_reputation_reasons: string;
  transfer_count: number;
  inbound_transfer_count: number;
  outbound_transfer_count: number;
  indirect_inbound_transfer_count: number;
  indirect_outbound_transfer_count: number;
  counterparty_count: number;
  sender_account_count: number;
  recipient_account_count: number;
  amount_decimal_sum: number | null;
  value_raw_sum: string;
};

export type CounterpartySummary = AccountEvidence & {
  chain_id: number;
  wallet_id: string;
  wallet_address: string;
  counterparty_address: string;
  token_status: TokenStatus;
  transfer_count: number;
  inbound_transfer_count: number;
  outbound_transfer_count: number;
  token_count: number;
  first_seen_at: string;
  last_seen_at: string;
};

export type TimelineRow = ClassificationEvidence & {
  wallet_id: string;
  wallet_address: string;
  block_date: string;
  token_address: string;
  token_symbol: string;
  token_status: TokenStatus;
  metadata_source: string | null;
  metadata_source_url: string | null;
  direction: "in" | "out";
  transfer_count: number;
  amount_decimal_sum: number | null;
  value_raw_sum: string;
};

export type WalletEvent = ClassificationEvidence & {
  transfer_id: string;
  chain_id: number;
  block_number: number;
  block_timestamp: string;
  block_date: string;
  transaction_hash: string;
  transaction_index: number;
  transaction_from_address: string | null;
  transaction_to_address: string | null;
  log_index: number;
  wallet_id: string;
  ens: string;
  wallet_address: string;
  from_address: string;
  to_address: string;
  direction: "in" | "out";
  transaction_sender_relation: TransactionSenderRelation;
  transaction_target_relation: TransactionTargetRelation;
  is_indirect: boolean | null;
  counterparty_address: string;
  counterparty_account_type: AccountType;
  counterparty_code_state: CodeState;
  counterparty_code_size_bytes: number | null;
  counterparty_observation_block_number: number | null;
  counterparty_observation_block_timestamp: string | null;
  counterparty_eip7702_delegation_target: string | null;
  counterparty_is_safe: boolean;
  counterparty_safe_verification_status: SafeVerificationStatus;
  counterparty_safe_version: string | null;
  counterparty_safe_singleton_address: string | null;
  counterparty_safe_owner_count: number | null;
  counterparty_safe_threshold: number | null;
  counterparty_is_erc4337_account: boolean;
  counterparty_erc4337_user_operation_count: number | null;
  counterparty_erc4337_first_observed_block: number | null;
  counterparty_erc4337_last_observed_block: number | null;
  counterparty_erc4337_entrypoint_address: string | null;
  counterparty_erc4337_entrypoint_version: string | null;
  counterparty_erc4337_entrypoint_source: string | null;
  counterparty_erc4337_entrypoint_deployment_block: string | null;
  counterparty_erc4337_effective_coverage: string | null;
  counterparty_erc4337_failed_ranges: string | null;
  counterparty_erc4337_block_chunk_size: number | null;
  counterparty_erc4337_address_batch_size: number | null;
  counterparty_evidence_fetch_status: EvidenceFetchStatus;
  counterparty_evidence_reason_codes: string;
  counterparty_evidence_coverage_scope: string | null;
  counterparty_evidence_coverage_start_block: number | null;
  counterparty_evidence_coverage_end_block: number | null;
  counterparty_evidence_schema_version: string | null;
  token_address: string;
  token_symbol: string | null;
  token_name: string | null;
  token_decimals: number | null;
  token_status: TokenStatus;
  metadata_source: string | null;
  metadata_source_url: string | null;
  token_label_reason: string | null;
  value_raw: string;
  amount_decimal: number | null;
};

export type PipelineMetadata = {
  wallet_id: string;
  ens: string;
  wallet_address: string;
  chain_id: number;
  data_source: "fixture" | "hyperindex";
  generated_at: string;
  transfer_count: number;
  token_count: number;
  counterparty_count: number;
  non_spam_transfer_count: number;
  non_spam_token_count: number;
  non_spam_counterparty_count: number;
  spam_transfer_count: number;
  spam_token_count: number;
  suspected_spam_transfer_count: number;
  suspected_spam_token_count: number;
  interaction_count: number;
  account_evidence_address_count: number;
  account_evidence_complete_count: number;
  safe_evidence_address_count: number;
  erc4337_evidence_address_count: number;
  account_evidence_observation_block_number_min: number;
  account_evidence_observation_block_number_max: number;
  account_evidence_observation_block_timestamp_min: string;
  account_evidence_observation_block_timestamp_max: string;
  account_evidence_coverage_scope: string;
  account_evidence_coverage_start_block: number | null;
  account_evidence_coverage_end_block: number;
  account_evidence_schema_version: string;
  token_summary_row_count: number;
  counterparty_summary_row_count: number;
  timeline_row_count: number;
  first_event_at: string | null;
  last_event_at: string | null;
  status_counts: Record<string, {
    transfer_count: number;
    token_count: number;
    counterparty_count: number;
  }>;
  exported_event_count: number;
  exported_interaction_count: number;
  exported_token_summary_count: number;
  exported_counterparty_summary_count: number;
  exported_timeline_row_count: number;
  event_export_limit_per_status: number;
  graph_interaction_export_limit_per_status: number;
  token_summary_export_limit_per_status: number;
  counterparty_ranking_limit_per_filter_selection: number;
  counterparty_token_status_combination_count: number;
  counterparty_account_filter_combination_count: number;
  counterparty_ranking_selection_count: number;
  counterparty_ranking_candidate_address_count: number;
  counterparty_rankings_exact_for_all_filter_selections: boolean;
  timeline_row_export_limit: number;
  is_sampled: boolean;
};

export type DashboardData = {
  graph: DashboardGraph;
  summaries: {
    tokens: TokenSummary[];
    counterparties: CounterpartySummary[];
  };
  timeline: TimelineRow[];
  events: WalletEvent[];
  metadata: PipelineMetadata;
};

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    throw new Error(`Could not load ${path} (HTTP ${response.status})`);
  }
  return response.json() as Promise<T>;
}

// The dashboard is static: all runtime data is loaded from generated JSON files.
export async function loadDashboardData(signal?: AbortSignal): Promise<DashboardData> {
  const [graph, summaries, timeline, events, metadata] = await Promise.all([
    fetchJson<DashboardGraph>("data/graph.json", signal),
    fetchJson<DashboardData["summaries"]>("data/summaries.json", signal),
    fetchJson<TimelineRow[]>("data/timeline.json", signal),
    fetchJson<WalletEvent[]>("data/events.json", signal),
    fetchJson<PipelineMetadata>("data/meta.json", signal),
  ]);

  return { graph, summaries, timeline, events, metadata };
}
