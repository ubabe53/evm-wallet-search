import type {
  AccountFilter,
  AccountType,
  CounterpartySummary,
  DashboardMetadata,
  RecognitionFilter,
  TimelineBucket,
  TimelineInterval,
  TimelineRow,
  TokenSummary,
} from "../data";

export const EVENT_PAGE_SIZE = 10;
export const DEFAULT_COUNTERPARTY_LIMIT = 10;
export const COUNTERPARTY_LIMITS = [10, 25, 50] as const;
export const ACCOUNT_FILTERS: AccountFilter[] = ["eoa_candidate", "contract"];
export const RECOGNITION_FILTERS: RecognitionFilter[] = ["all", "recognized", "other"];
const ETHERSCAN_BASE_URL = "https://etherscan.io";
export const INDIRECT_TRANSFER_EXPLANATION = "Top-level transaction sender differs from Transfer.from. This can happen with transferFrom, routers, Safe/account abstraction, or synthetic event emission; the mismatch alone does not prove intent or legitimacy.";
export const SELF_TRANSFER_EXPLANATION = "Transfer.from and Transfer.to are both the tracked wallet. The event is preserved once, but it is neither inbound nor outbound and has no external counterparty.";

export function etherscanAddressUrl(address: string): string {
  return `${ETHERSCAN_BASE_URL}/address/${address}`;
}

export function etherscanTokenUrl(address: string): string {
  return `${ETHERSCAN_BASE_URL}/token/${address}`;
}

export function etherscanTransactionUrl(hash: string): string {
  return `${ETHERSCAN_BASE_URL}/tx/${hash}`;
}

export function snapshotCoverageLabel(
  metadata: Pick<
    DashboardMetadata,
    "snapshot_start_block" | "snapshot_end_block" | "snapshot_finality_policy"
  >,
): string {
  if (
    metadata.snapshot_start_block == null ||
    metadata.snapshot_end_block == null ||
    metadata.snapshot_finality_policy !== "ethereum_finalized"
  ) {
    return "Coverage not recorded";
  }
  return `Blocks ${metadata.snapshot_start_block.toLocaleString("en-US")}–${metadata.snapshot_end_block.toLocaleString("en-US")} · Finalized`;
}

export function shortAddress(address: string): string {
  if (address.length <= 14) {
    return address;
  }
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function compactAddress(address: string): string {
  if (address.length <= 12) {
    return address;
  }
  return `${address.slice(0, 5)}...${address.slice(-3)}`;
}

export function generatedAtLabel(value: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  }).format(new Date(value));
}

export type RankedCounterparty = Omit<CounterpartySummary, "recognition_status">;
export type DisplayedTokenSummary = Omit<TokenSummary, "counterparty_account_type">;
export type DisplayedTimelineRow = Omit<TimelineRow, "counterparty_account_type">;

export function aggregateTokenSummaries(rows: TokenSummary[]): DisplayedTokenSummary[] {
  const grouped = new Map<string, DisplayedTokenSummary>();

  for (const row of rows) {
    const existing = grouped.get(row.token_address);
    if (!existing) {
      const {
        counterparty_account_type: _accountType,
        ...summary
      } = row;
      grouped.set(row.token_address, { ...summary });
      continue;
    }

    existing.transfer_count += row.transfer_count;
    existing.inbound_transfer_count += row.inbound_transfer_count;
    existing.outbound_transfer_count += row.outbound_transfer_count;
    existing.self_transfer_count += row.self_transfer_count;
    existing.indirect_inbound_transfer_count += row.indirect_inbound_transfer_count;
    existing.indirect_outbound_transfer_count += row.indirect_outbound_transfer_count;
    existing.counterparty_count += row.counterparty_count;
    existing.sender_account_count += row.sender_account_count;
    existing.recipient_account_count += row.recipient_account_count;
  }

  return [...grouped.values()].sort((left, right) =>
    right.transfer_count - left.transfer_count ||
    left.token_address.localeCompare(right.token_address),
  );
}

export function aggregateTimelineRows(rows: TimelineRow[]): DisplayedTimelineRow[] {
  const grouped = new Map<string, DisplayedTimelineRow>();

  for (const row of rows) {
    const key = [
      row.chain_id,
      row.wallet_address,
      row.block_date,
      row.token_address,
      row.recognition_status,
      row.direction,
    ].join("|");
    const existing = grouped.get(key);
    if (!existing) {
      const {
        counterparty_account_type: _accountType,
        ...timelineRow
      } = row;
      grouped.set(key, { ...timelineRow });
      continue;
    }

    existing.transfer_count += row.transfer_count;
  }

  return [...grouped.values()].sort((left, right) =>
    left.block_date.localeCompare(right.block_date) ||
    left.token_symbol.localeCompare(right.token_symbol) ||
    left.direction.localeCompare(right.direction) ||
    left.token_address.localeCompare(right.token_address),
  );
}

export function aggregateCounterparties(rows: CounterpartySummary[]): RankedCounterparty[] {
  const grouped = new Map<string, RankedCounterparty>();

  for (const row of rows) {
    const existing = grouped.get(row.counterparty_address);
    if (!existing) {
      const { recognition_status: _recognitionStatus, ...summary } = row;
      grouped.set(row.counterparty_address, { ...summary });
      continue;
    }

    existing.transfer_count += row.transfer_count;
    existing.inbound_transfer_count += row.inbound_transfer_count;
    existing.outbound_transfer_count += row.outbound_transfer_count;
    existing.token_count += row.token_count;
    existing.first_seen_at = existing.first_seen_at < row.first_seen_at ? existing.first_seen_at : row.first_seen_at;
    existing.last_seen_at = existing.last_seen_at > row.last_seen_at ? existing.last_seen_at : row.last_seen_at;
  }

  return [...grouped.values()].sort((left, right) =>
    right.transfer_count - left.transfer_count ||
    right.last_seen_at.localeCompare(left.last_seen_at) ||
    left.counterparty_address.localeCompare(right.counterparty_address),
  );
}

export function accountEvidenceObservationBlockLabel(minimum: number | null, maximum: number | null): string {
  if (minimum == null || maximum == null) {
    return "not collected";
  }
  if (minimum === maximum) {
    return `block ${minimum.toLocaleString("en-US")}`;
  }
  return `blocks ${minimum.toLocaleString("en-US")}–${maximum.toLocaleString("en-US")}`;
}

export function accountEvidenceObservationTimeLabel(minimum: string | null, maximum: string | null): string {
  if (minimum == null || maximum == null) {
    return "not collected";
  }
  return minimum === maximum ? minimum : `${minimum}–${maximum}`;
}

function coverageRateLabel(classified: number, eligible: number): string {
  if (eligible === 0) {
    return "not applicable";
  }
  return `${(classified / eligible * 100).toLocaleString("en-US", {
    maximumFractionDigits: 1,
  })}%`;
}

export function accountEvidenceCoverageLabel(
  metadata: Pick<
    DashboardMetadata,
    "account_evidence_classified_address_count" | "account_evidence_eligible_address_count"
  >,
): string {
  return `address types ${metadata.account_evidence_classified_address_count.toLocaleString("en-US")}/${metadata.account_evidence_eligible_address_count.toLocaleString("en-US")}`;
}

export function accountEvidenceCoverageDescription(
  metadata: Pick<
    DashboardMetadata,
    | "account_evidence_classified_address_count"
    | "account_evidence_eligible_address_count"
    | "account_evidence_failed_address_count"
    | "account_evidence_not_checked_address_count"
    | "account_evidence_classified_event_count"
    | "account_evidence_eligible_event_count"
    | "account_evidence_observation_block_timestamp_min"
    | "account_evidence_observation_block_timestamp_max"
  >,
): string {
  return [
    `${metadata.account_evidence_classified_address_count.toLocaleString("en-US")} of ${metadata.account_evidence_eligible_address_count.toLocaleString("en-US")} nonzero, nonself counterparties classified (${coverageRateLabel(metadata.account_evidence_classified_address_count, metadata.account_evidence_eligible_address_count)})`,
    `${metadata.account_evidence_classified_event_count.toLocaleString("en-US")} of ${metadata.account_evidence_eligible_event_count.toLocaleString("en-US")} captured transfers have classified counterparties (${coverageRateLabel(metadata.account_evidence_classified_event_count, metadata.account_evidence_eligible_event_count)})`,
    `${metadata.account_evidence_failed_address_count.toLocaleString("en-US")} failed; ${metadata.account_evidence_not_checked_address_count.toLocaleString("en-US")} not checked`,
    `successful observations at ${accountEvidenceObservationTimeLabel(metadata.account_evidence_observation_block_timestamp_min, metadata.account_evidence_observation_block_timestamp_max)}`,
  ].join("; ");
}


export const ACCOUNT_LABELS: Record<AccountFilter, string> = {
  eoa_candidate: "EOA",
  contract: "Contract",
};

export function accountMatches(
  accountType: AccountType,
  selected: AccountFilter[],
): boolean {
  return selected.length === ACCOUNT_FILTERS.length || selected.some((value) => value === accountType);
}


export function utcDate(value: string): Date {
  return new Date(`${value}T00:00:00Z`);
}

function isoDate(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function bucketStart(value: string, interval: TimelineInterval): string {
  const date = utcDate(value);
  if (interval === "month") {
    date.setUTCDate(1);
  } else {
    date.setUTCMonth(0, 1);
  }
  return isoDate(date);
}

function nextBucket(value: string, interval: TimelineInterval): string {
  const date = utcDate(value);
  if (interval === "month") {
    date.setUTCMonth(date.getUTCMonth() + 1);
  } else {
    date.setUTCFullYear(date.getUTCFullYear() + 1);
  }
  return isoDate(date);
}

export function bucketTimelineRows(
  rows: readonly Pick<TimelineRow, "block_date" | "direction" | "transfer_count">[],
  interval: TimelineInterval,
  selectedYear: number | null = null,
  availableYears: readonly number[] = [],
): TimelineBucket[] {
  if (interval === "month" && selectedYear == null) {
    return [];
  }
  const counts = new Map<string, TimelineBucket>();
  for (const row of rows) {
    if (selectedYear != null && utcDate(row.block_date).getUTCFullYear() !== selectedYear) {
      continue;
    }
    const start = bucketStart(row.block_date, interval);
    const current = counts.get(start) ?? {
      bucket_start: start,
      bucket_end: nextBucket(start, interval),
      transfer_count: 0,
      inbound_transfer_count: 0,
      outbound_transfer_count: 0,
      self_transfer_count: 0,
    };
    current.transfer_count += row.transfer_count;
    if (row.direction === "in") {
      current.inbound_transfer_count += row.transfer_count;
    } else if (row.direction === "out") {
      current.outbound_transfer_count += row.transfer_count;
    } else {
      current.self_transfer_count += row.transfer_count;
    }
    counts.set(start, current);
  }
  const starts = [...counts.keys()].sort();
  const first = interval === "month"
    ? `${selectedYear}-01-01`
    : availableYears.length > 0
      ? `${Math.min(...availableYears)}-01-01`
      : starts[0];
  const last = interval === "month"
    ? `${selectedYear}-12-01`
    : availableYears.length > 0
      ? `${Math.max(...availableYears)}-01-01`
      : starts[starts.length - 1];
  if (!first || !last) {
    return [];
  }
  const buckets: TimelineBucket[] = [];
  for (let start = first; start <= last; start = nextBucket(start, interval)) {
    buckets.push(counts.get(start) ?? {
      bucket_start: start,
      bucket_end: nextBucket(start, interval),
      transfer_count: 0,
      inbound_transfer_count: 0,
      outbound_transfer_count: 0,
      self_transfer_count: 0,
    });
  }
  return buckets;
}

export function timelinePeriodLabel(
  bucket: Pick<TimelineBucket, "bucket_start" | "bucket_end">,
  interval: TimelineInterval,
): string {
  const start = utcDate(bucket.bucket_start);
  return interval === "month"
    ? new Intl.DateTimeFormat("en-US", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(start)
    : String(start.getUTCFullYear());
}

export function timelineTickLabel(bucket: TimelineBucket, interval: TimelineInterval): string {
  const start = utcDate(bucket.bucket_start);
  return interval === "year"
    ? String(start.getUTCFullYear())
    : new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" }).format(start);
}

export function timelineYears(firstEventAt: string | null, lastEventAt: string | null): number[] {
  if (!firstEventAt || !lastEventAt) {
    return [];
  }
  const firstYear = new Date(firstEventAt).getUTCFullYear();
  const lastYear = new Date(lastEventAt).getUTCFullYear();
  return Array.from({ length: lastYear - firstYear + 1 }, (_, index) => firstYear + index);
}

export function timelineScaleTicks(maximum: number): number[] {
  if (maximum <= 0) {
    return [0];
  }
  return [1, 0.75, 0.5, 0.25, 0].map((position) => maximum * position);
}

export function timelineScaleLabel(value: number, maximum: number): string {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: maximum < 100 ? 2 : 0,
  });
}
