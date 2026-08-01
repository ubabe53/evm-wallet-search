export type RecognitionStatus = "recognized" | "other";
export type RecognitionFilter = "all" | RecognitionStatus;
export type AccountType = "eoa_candidate" | "contract" | "unknown";
export type AccountFilter = Exclude<AccountType, "unknown">;
export type CodeState = "no_code" | "eip7702_delegated" | "contract_code" | "unknown";
export type TransferDirection = "in" | "out" | "self";

export type AccountEvidence = {
  account_type: AccountType;
  code_state: CodeState;
  observation_block_number: number | null;
  eip7702_delegation_target: string | null;
};

export type TokenSummary = {
  chain_id: number;
  wallet_address: string;
  token_address: string;
  token_symbol: string;
  token_name: string | null;
  recognition_status: RecognitionStatus;
  recognition_override_status?: RecognitionStatus | null;
  counterparty_account_type?: AccountType;
  transfer_count: number;
  inbound_transfer_count: number;
  outbound_transfer_count: number;
  self_transfer_count: number;
  indirect_inbound_transfer_count: number;
  indirect_outbound_transfer_count: number;
  counterparty_count: number;
  sender_account_count: number;
  recipient_account_count: number;
};

export type CounterpartySummary = AccountEvidence & {
  chain_id: number;
  wallet_address: string;
  counterparty_address: string;
  recognition_status?: RecognitionStatus;
  transfer_count: number;
  inbound_transfer_count: number;
  outbound_transfer_count: number;
  token_count: number;
  first_seen_at: string;
  last_seen_at: string;
};

export type TimelineRow = {
  chain_id: number;
  wallet_address: string;
  block_date: string;
  token_address: string;
  token_symbol: string;
  recognition_status: RecognitionStatus;
  counterparty_account_type: AccountType;
  direction: TransferDirection;
  transfer_count: number;
};

export type WalletEvent = {
  transfer_id: string;
  chain_id: number;
  wallet_address: string;
  block_number: number;
  block_timestamp: string;
  transaction_hash: string;
  transaction_index: number;
  log_index: number;
  token_address: string;
  token_symbol: string | null;
  token_name: string | null;
  recognition_status: RecognitionStatus;
  direction: TransferDirection;
  is_indirect: boolean | null;
  counterparty_address: string;
  counterparty_account_type: AccountType;
  counterparty_code_state: CodeState;
  counterparty_observation_block_number: number | null;
  counterparty_eip7702_delegation_target: string | null;
};

type ArtifactMetadata = {
  configured_wallet_label: string;
  wallet_address: string;
  chain_id: number;
  data_source: "fixture" | "hyperindex";
  generated_at: string;
  snapshot_run_id: string | null;
  snapshot_start_block: number | null;
  snapshot_end_block: number | null;
  snapshot_end_block_hash: string | null;
  snapshot_finality_policy: "ethereum_finalized" | null;
  snapshot_scope_version: string | null;
  transfer_count: number;
  event_block_number_min: number | null;
  event_block_number_max: number | null;
  first_event_at: string | null;
  last_event_at: string | null;
  account_evidence_population_scope: "distinct_nonzero_nonself_event_counterparties";
  account_evidence_eligible_address_count: number;
  account_evidence_classified_address_count: number;
  account_evidence_failed_address_count: number;
  account_evidence_not_checked_address_count: number;
  account_evidence_eligible_event_count: number;
  account_evidence_classified_event_count: number;
  account_evidence_failed_event_count: number;
  account_evidence_not_checked_event_count: number;
  account_evidence_observation_block_number_min: number | null;
  account_evidence_observation_block_number_max: number | null;
  account_evidence_observation_block_timestamp_min: string | null;
  account_evidence_observation_block_timestamp_max: string | null;
  account_evidence_schema_version: string | null;
};

export type PipelineMetadata = ArtifactMetadata & {
  export_schema_version: "dashboard-export-v1";
  completeness_scope: "duckdb_snapshot";
  indexer_checkpoint_recorded: false;
  finality_status: "not_recorded";
  complete_event_count: number;
  complete_token_summary_row_count: number;
  complete_counterparty_summary_row_count: number;
  complete_timeline_row_count: number;
  recognition_counts: Record<string, {
    transfer_count: number;
    token_count: number;
    counterparty_count: number;
  }>;
  recognition_account_counts: Record<string, {
    transfer_count: number;
    token_count: number;
    counterparty_count: number;
  }>;
  exported_event_count: number;
  exported_token_summary_count: number;
  exported_counterparty_summary_count: number;
  exported_timeline_row_count: number;
  recognition_account_evidence_cell_count: number;
  event_export_limit_per_recognition_account_evidence: number;
  token_summary_ranking_limit_per_recognition_account_selection: number;
  token_summary_ranking_selection_count: number;
  token_summary_ranking_candidate_token_count: number;
  token_summary_rankings_exact_for_all_filter_selections: boolean;
  counterparty_ranking_limit_per_recognition_account_selection: number;
  counterparty_recognition_combination_count: number;
  counterparty_account_filter_combination_count: number;
  counterparty_ranking_selection_count: number;
  counterparty_ranking_candidate_address_count: number;
  counterparty_rankings_exact_for_all_filter_selections: boolean;
  timeline_row_export_limit_per_recognition_account_evidence: number;
  is_sampled: boolean;
};

export type ApiMetadata = ArtifactMetadata & {
  api_schema_version: "dashboard-api-v16";
  database_mode: "live" | "fixture_test";
  completeness_scope: "duckdb_snapshot" | "finalized_block_range";
  indexer_checkpoint_recorded: boolean;
  finality_status: "not_recorded" | "finalized";
  is_sampled: false;
};

export type DashboardMetadata = PipelineMetadata | ApiMetadata;

export type DashboardData<Metadata extends DashboardMetadata = PipelineMetadata> = {
  summaries: {
    tokens: TokenSummary[];
    counterparties: CounterpartySummary[];
  };
  timeline: TimelineRow[];
  events: WalletEvent[];
  metadata: Metadata;
};

export type DashboardQuery = {
  walletAddress: string | null;
  recognition: RecognitionFilter;
  accountFilters: AccountFilter[];
  query: string;
  counterpartyLimit: number;
  timelineInterval: TimelineInterval;
  timelineYear: number | null;
  startDate: string | null;
  endDate: string | null;
};

export type TimelineInterval = "month" | "year";

export type TimelineBucket = {
  bucket_start: string;
  bucket_end: string;
  transfer_count: number;
  inbound_transfer_count: number;
  outbound_transfer_count: number;
  self_transfer_count: number;
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
  timelineBuckets: TimelineBucket[];
  summary: DashboardSummary;
  eventCount: number;
  eventNextCursor: string | null;
  tokenCount: number;
  counterpartyCount: number;
};

export type ScanJob = {
  job_id: string;
  requested_value: string;
  wallet_address: string;
  wallet_label: string;
  status: "queued" | "running" | "completed" | "failed";
  progress: number;
  from_block: number;
  to_block: number;
  error: string | null;
  created_at: string;
  updated_at: string;
  resolver_source?: string | null;
  observation_block_number?: number | null;
  observation_block_hash?: string | null;
  observation_timestamp?: string | null;
};

export type WalletListItem = {
  chain_id: number;
  wallet_address: string;
  label: string;
  status: "completed";
};

export const dashboardDataMode = import.meta.env.VITE_DATA_MODE === "api" ? "api" : "static";

function apiQuery(query: DashboardQuery, extra: Record<string, string | number> = {}): string {
  const parameters = new URLSearchParams();
  if (query.walletAddress) {
    parameters.set("wallet_address", query.walletAddress);
  }
  parameters.set("recognition", query.recognition);
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
  if (query.startDate && query.endDate) {
    parameters.set("start", query.startDate);
    parameters.set("end", query.endDate);
  }
  for (const [key, value] of Object.entries(extra)) {
    parameters.set(key, String(value));
  }
  return parameters.toString();
}

async function fetchJson<T>(path: string, signal?: AbortSignal, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, signal });
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
  const [summaries, timeline, events, metadata] = await Promise.all([
    fetchJson<DashboardData["summaries"]>("data/summaries.json", signal),
    fetchJson<TimelineRow[]>("data/timeline.json", signal),
    fetchJson<WalletEvent[]>("data/events.json", signal),
    fetchJson<PipelineMetadata>("data/meta.json", signal),
  ]);

  return { summaries, timeline, events, metadata };
}

export async function loadApiDashboardData(
  query: DashboardQuery,
  signal?: AbortSignal,
  cachedMetadata?: ApiMetadata,
): Promise<ApiDashboardData> {
  const common = apiQuery(query);
  const metadataPath = query.walletAddress
    ? `/api/v1/metadata?wallet_address=${encodeURIComponent(query.walletAddress)}`
    : "/api/v1/metadata";
  // Bound concurrent DuckDB readers: a dashboard refresh must not fan out six
  // analytical scans at once on a developer laptop.
  const [metadata, summary] = await Promise.all([
    cachedMetadata ?? fetchJson<ApiMetadata>(metadataPath, signal),
    fetchJson<DashboardSummary>(`/api/v1/summary?${common}`, signal),
  ]);
  const timelineQuery = { ...query, startDate: null, endDate: null };
  const timelineParameters: Record<string, string | number> = {
    interval: query.timelineInterval,
  };
  if (query.timelineYear != null) {
    timelineParameters.year = query.timelineYear;
  }
  const [events, timeline] = await Promise.all([
    fetchJson<ApiCollection<WalletEvent>>(`/api/v1/events?${apiQuery(query, { limit: 10 })}`, signal),
    fetchJson<ApiCollection<TimelineBucket> & { interval: TimelineInterval; year: number | null }>(
      `/api/v1/timeline?${apiQuery(timelineQuery, timelineParameters)}`,
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
      summaries: { tokens: tokens.items, counterparties: counterparties.items },
      timeline: [],
      events: events.items,
      metadata,
    },
    timelineBuckets: timeline.items,
    summary,
    eventCount: events.complete_matching_count,
    eventNextCursor: events.next_cursor ?? null,
    tokenCount: tokens.complete_matching_count,
    counterpartyCount: counterparties.complete_matching_count,
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
  return response;
}

export type RecognitionOverrideResponse = {
  chain_id: 1;
  token_address: string;
  automatic_status: RecognitionStatus;
  override_status: RecognitionStatus | null;
  recognition_status: RecognitionStatus;
  recognition_source: "automatic" | "manual";
  previous_override_status: RecognitionStatus | null;
};

export function setTokenRecognition(
  tokenAddress: string,
  status: RecognitionStatus,
  signal?: AbortSignal,
): Promise<RecognitionOverrideResponse> {
  return fetchJson(`/api/v1/tokens/${encodeURIComponent(tokenAddress)}/recognition`, signal, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
}

export function resetTokenRecognition(
  tokenAddress: string,
  signal?: AbortSignal,
): Promise<RecognitionOverrideResponse> {
  return fetchJson(`/api/v1/tokens/${encodeURIComponent(tokenAddress)}/recognition`, signal, {
    method: "DELETE",
  });
}

export function createScanJob(wallet: string, signal?: AbortSignal): Promise<ScanJob> {
  return fetchJson<ScanJob>("/api/v1/scan-jobs", signal, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wallet }),
  });
}

export function loadScanJob(jobId: string, signal?: AbortSignal): Promise<ScanJob> {
  return fetchJson<ScanJob>(`/api/v1/scan-jobs/${encodeURIComponent(jobId)}`, signal);
}

export function loadWallets(signal?: AbortSignal): Promise<{ items: WalletListItem[] }> {
  return fetchJson<{ items: WalletListItem[] }>("/api/v1/wallets", signal);
}
