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
    metadataAvailability?: MetadataAvailability;
    tokenQuality?: TokenQuality;
    tokenQualitySources?: string[];
    tokenQualitySourceCount?: number;
    tokenQualityReason?: string;
    tokenQualityProvenance?: string;
    tokenQualityVersion?: "token-quality-v1";
    metadataSource?: string | null;
    metadataSourceUrl?: string | null;
    tokenReputation?: TokenReputation;
    tokenReputationScore?: number;
    tokenReputationReasons?: string;
    tokenReputationVersion?: "token-reputation-v2";
    interactionLegitimacy?: InteractionLegitimacy;
    interactionLegitimacyScore?: number;
    interactionLegitimacyReasons?: string;
    counterpartyAccountType: AccountType;
    transferCount: number;
    counterpartyTransferCount: number;
    amountDecimalSum?: number | null;
  };
};

export type TokenStatus = "trusted" | "unverified" | "suspected_spam" | "spam";
export type TokenReputation = TokenStatus;
export type TokenQuality = "high_confidence" | "listed" | "unknown";
export type MetadataAvailability = "complete" | "partial" | "unavailable";
export type InteractionLegitimacy = "not_suspicious" | "uncertain" | "suspicious";
export type TransactionSenderRelation = "transfer_sender" | "transfer_recipient" | "other" | "unknown";
export type TransactionTargetRelation = "token_contract" | "transfer_sender" | "transfer_recipient" | "other" | "unknown";
export type AccountType = "eoa_candidate" | "contract" | "unknown";
export type AccountFilter = Exclude<AccountType, "unknown">;
export type CodeState = "no_code" | "eip7702_delegated" | "contract_code" | "unknown";
export type EvidenceFetchStatus = "complete" | "failed" | "not_fetched";

export type AccountEvidence = {
  account_type: AccountType;
  code_state: CodeState;
  code_size_bytes: number | null;
  observation_block_number: number | null;
  observation_block_timestamp: string | null;
  eip7702_delegation_target: string | null;
  evidence_fetch_status: EvidenceFetchStatus;
  evidence_reason_codes: string;
  evidence_coverage_scope: string | null;
  evidence_coverage_start_block: number | null;
  evidence_coverage_end_block: number | null;
  evidence_schema_version: string | null;
};

export type ClassificationEvidence = {
  metadata_availability: MetadataAvailability;
  token_quality: TokenQuality;
  token_quality_sources: string[];
  token_quality_source_count: number;
  token_quality_reason: string;
  token_quality_provenance: string;
  token_quality_version: "token-quality-v1";
  token_reputation: TokenReputation;
  token_reputation_score: number;
  token_reputation_reasons: string;
  token_reputation_version: "token-reputation-v2";
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
  metadata_availability: MetadataAvailability;
  token_quality: TokenQuality;
  token_quality_sources: string[];
  token_quality_source_count: number;
  token_quality_reason: string;
  token_quality_provenance: string;
  token_quality_version: "token-quality-v1";
  token_reputation: TokenReputation;
  token_reputation_score: number;
  token_reputation_reasons: string;
  token_reputation_version: "token-reputation-v2";
  counterparty_account_type: AccountType;
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
  token_quality: TokenQuality;
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
  counterparty_account_type: AccountType;
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
  account_evidence_observation_block_number_min: number | null;
  account_evidence_observation_block_number_max: number | null;
  account_evidence_observation_block_timestamp_min: string | null;
  account_evidence_observation_block_timestamp_max: string | null;
  account_evidence_coverage_scope: string | null;
  account_evidence_coverage_start_block: number | null;
  account_evidence_coverage_end_block: number | null;
  account_evidence_schema_version: string | null;
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
  quality_counts: Record<string, {
    transfer_count: number;
    token_count: number;
    counterparty_count: number;
  }>;
  status_quality_counts: Record<string, {
    transfer_count: number;
    token_count: number;
    counterparty_count: number;
  }>;
  status_quality_account_counts: Record<string, {
    transfer_count: number;
    token_count: number;
    counterparty_count: number;
  }>;
  exported_event_count: number;
  exported_interaction_count: number;
  exported_token_summary_count: number;
  exported_counterparty_summary_count: number;
  exported_timeline_row_count: number;
  status_quality_account_evidence_cell_count: number;
  event_export_limit_per_status_quality_account_evidence: number;
  graph_interaction_export_limit_per_status_quality_account_evidence: number;
  token_summary_ranking_limit_per_status_quality_account_selection: number;
  token_summary_ranking_selection_count: number;
  token_summary_ranking_candidate_token_count: number;
  token_summary_rankings_exact_for_all_filter_selections: boolean;
  counterparty_ranking_limit_per_status_quality_account_selection: number;
  counterparty_token_status_combination_count: number;
  counterparty_token_quality_combination_count: number;
  counterparty_account_filter_combination_count: number;
  counterparty_ranking_selection_count: number;
  counterparty_ranking_candidate_address_count: number;
  counterparty_rankings_exact_for_all_filter_selections: boolean;
  timeline_row_export_limit_per_status_quality_account_evidence: number;
  is_sampled: boolean;
};

export type ApiMetadata = {
  wallet_id: string;
  ens: string;
  wallet_address: string;
  chain_id: number;
  data_source: "fixture" | "hyperindex";
  generated_at: string;
  transfer_count: number;
  spam_transfer_count: number;
  first_event_at: string | null;
  last_event_at: string | null;
  account_evidence_observation_block_number_min: number | null;
  account_evidence_observation_block_number_max: number | null;
  account_evidence_observation_block_timestamp_min: string | null;
  account_evidence_observation_block_timestamp_max: string | null;
  account_evidence_coverage_scope: string | null;
  account_evidence_coverage_start_block: number | null;
  account_evidence_coverage_end_block: number | null;
  account_evidence_schema_version: string | null;
  event_block_number_min: number | null;
  event_block_number_max: number | null;
  api_schema_version: string;
  database_mode: "live" | "fixture_test";
  completeness_scope: "duckdb_snapshot";
  indexer_checkpoint_recorded: false;
  finality_status: "not_recorded";
  is_sampled: false;
};

export type DashboardMetadata = PipelineMetadata | ApiMetadata;

export type DashboardData<Metadata extends DashboardMetadata = PipelineMetadata> = {
  graph: DashboardGraph;
  summaries: {
    tokens: TokenSummary[];
    counterparties: CounterpartySummary[];
  };
  timeline: TimelineRow[];
  events: WalletEvent[];
  metadata: Metadata;
};

export type DashboardQuery = {
  includeSpam: boolean;
  accountFilters: AccountFilter[];
  query: string;
  graphLimit: number;
  counterpartyLimit: number;
};

export type DashboardSummary = {
  transfer_count: number;
  token_count: number;
  counterparty_count: number;
};

export type ApiCollection<T> = {
  complete_matching_count: number;
  returned_count: number;
  next_cursor?: string | null;
  is_truncated?: boolean;
  items: T[];
};

export type ApiDashboardData = {
  data: DashboardData<ApiMetadata>;
  summary: DashboardSummary;
  eventCount: number;
  eventNextCursor: string | null;
  tokenCount: number;
  counterpartyCount: number;
  graphInteractionCount: number;
};

type ApiGraphInteraction = {
  wallet_id: string;
  ens: string;
  wallet_address: string;
  counterparty_address: string;
  token_address: string;
  token_symbol: string;
  token_status: TokenStatus;
  direction: "in" | "out";
  account_type: AccountType;
  observation_block_number: number | null;
  eip7702_delegation_target: string | null;
  evidence_coverage_start_block: number | null;
  evidence_coverage_end_block: number | null;
  transfer_count: number;
  counterparty_transfer_count: number;
};

export const dashboardDataMode = import.meta.env.VITE_DATA_MODE === "api" ? "api" : "static";

function apiQuery(query: DashboardQuery, extra: Record<string, string | number> = {}): string {
  const parameters = new URLSearchParams();
  parameters.set("include_spam", String(query.includeSpam));
  if (query.accountFilters.length === 0) {
    parameters.append("account", "none");
  } else if (query.accountFilters.length < 2) {
    for (const account of query.accountFilters) {
      parameters.append("account", account);
    }
  }
  if (query.query.trim()) {
    parameters.set("q", query.query.trim());
  }
  for (const [key, value] of Object.entries(extra)) {
    parameters.set(key, String(value));
  }
  return parameters.toString();
}

function apiGraph(items: ApiGraphInteraction[]): DashboardGraph {
  const nodes = new Map<string, GraphNode>();
  const edges: GraphEdge[] = [];

  for (const item of items) {
    const walletNodeId = `wallet:${item.wallet_address}`;
    const counterpartyNodeId = `counterparty:${item.counterparty_address}`;
    const interactionId = `interaction:${item.wallet_address}:${item.counterparty_address}:${item.token_address}:${item.direction}`;
    nodes.set(walletNodeId, {
      data: {
        id: walletNodeId, label: item.ens, type: "wallet", address: item.wallet_address,
        tokenAddress: null, symbol: null, accountType: null, codeState: null,
        observationBlockNumber: null, observationBlockTimestamp: null,
        eip7702DelegationTarget: null, evidenceFetchStatus: null,
        evidenceReasonCodes: null, evidenceCoverageStartBlock: null, evidenceCoverageEndBlock: null,
      },
    });
    nodes.set(counterpartyNodeId, {
      data: {
        id: counterpartyNodeId,
        label: `${item.counterparty_address.slice(0, 6)}...${item.counterparty_address.slice(-4)}`,
        type: "counterparty",
        address: item.counterparty_address, tokenAddress: null, symbol: null,
        accountType: item.account_type, codeState: null,
        observationBlockNumber: item.observation_block_number, observationBlockTimestamp: null,
        eip7702DelegationTarget: item.eip7702_delegation_target, evidenceFetchStatus: null,
        evidenceReasonCodes: null, evidenceCoverageStartBlock: item.evidence_coverage_start_block,
        evidenceCoverageEndBlock: item.evidence_coverage_end_block,
      },
    });
    edges.push({
      data: {
        id: `${interactionId}:wallet-counterparty`, interactionId, edgeRole: "wallet_counterparty",
        source: item.direction === "out" ? walletNodeId : counterpartyNodeId,
        target: item.direction === "out" ? counterpartyNodeId : walletNodeId,
        walletAddress: item.wallet_address, counterpartyAddress: item.counterparty_address,
        direction: item.direction, tokenAddress: item.token_address, tokenSymbol: item.token_symbol,
        tokenStatus: item.token_status,
        counterpartyAccountType: item.account_type, transferCount: item.transfer_count,
        counterpartyTransferCount: item.counterparty_transfer_count,
      },
    });
  }
  return { nodes: [...nodes.values()], edges };
}

function normalizeEvent(event: WalletEvent): WalletEvent {
  return {
    ...event,
    amount_decimal: event.amount_decimal == null ? null : Number(event.amount_decimal),
  };
}

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal });
  if (!response.ok) {
    const payload = typeof response.json === "function"
      ? await response.json().catch(() => null) as { detail?: string } | null
      : null;
    throw new Error(payload?.detail ?? `Could not load ${path} (HTTP ${response.status})`);
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

export async function loadApiDashboardData(
  query: DashboardQuery,
  signal?: AbortSignal,
  cachedMetadata?: ApiMetadata,
): Promise<ApiDashboardData> {
  const common = apiQuery(query);
  // Bound concurrent DuckDB readers: a dashboard refresh must not fan out six
  // analytical scans at once on a developer laptop.
  const [metadata, summary] = await Promise.all([
    cachedMetadata ?? fetchJson<ApiMetadata>("/api/v1/metadata", signal),
    fetchJson<DashboardSummary>(`/api/v1/summary?${common}`, signal),
  ]);
  const [events, graph] = await Promise.all([
    fetchJson<ApiCollection<WalletEvent>>(`/api/v1/events?${apiQuery(query, { limit: 10 })}`, signal),
    fetchJson<ApiCollection<ApiGraphInteraction>>(
      `/api/v1/graph?${apiQuery(query, { limit: query.graphLimit })}`,
      signal,
    ),
  ]);
  const [tokens, counterparties] = await Promise.all([
    fetchJson<ApiCollection<TokenSummary>>(`/api/v1/tokens?${apiQuery(query, { limit: 500 })}`, signal),
    fetchJson<ApiCollection<CounterpartySummary>>(
      `/api/v1/counterparties?${apiQuery(query, { limit: query.counterpartyLimit })}`,
      signal,
    ),
  ]);

  return {
    data: {
      graph: apiGraph(graph.items),
      summaries: { tokens: tokens.items, counterparties: counterparties.items },
      timeline: [],
      events: events.items.map(normalizeEvent),
      metadata,
    },
    summary,
    eventCount: events.complete_matching_count,
    eventNextCursor: events.next_cursor ?? null,
    tokenCount: tokens.complete_matching_count,
    counterpartyCount: counterparties.complete_matching_count,
    graphInteractionCount: graph.complete_matching_count,
  };
}

export async function loadNextApiEvents(
  query: DashboardQuery,
  cursor: string,
  signal?: AbortSignal,
): Promise<ApiCollection<WalletEvent>> {
  const response = await fetchJson<ApiCollection<WalletEvent>>(
    `/api/v1/events?${apiQuery(query, { limit: 10, cursor })}`,
    signal,
  );
  return { ...response, items: response.items.map(normalizeEvent) };
}
