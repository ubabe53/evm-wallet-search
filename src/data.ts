export type GraphNode = {
  data: {
    id: string;
    label: string;
    type: "wallet" | "counterparty" | "token";
    address: string | null;
    tokenAddress: string | null;
    symbol: string | null;
    addressType: AddressType | null;
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
export type AddressType = "contract" | "wallet" | "unknown";

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

export type TokenSummary = ClassificationEvidence & {
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
  direction: "in" | "out";
  transfer_count: number;
  amount_decimal_sum: number | null;
  value_raw_sum: string;
};

export type CounterpartySummary = {
  wallet_id: string;
  wallet_address: string;
  counterparty_address: string;
  counterparty_type: AddressType;
  direction: "in" | "out";
  transfer_count: number;
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
  log_index: number;
  wallet_id: string;
  ens: string;
  wallet_address: string;
  direction: "in" | "out";
  counterparty_address: string;
  counterparty_type: AddressType;
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
  counterparty_summary_export_limit: number;
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
