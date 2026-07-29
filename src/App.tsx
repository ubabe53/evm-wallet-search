import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  Database,
  ExternalLink,
  Info,
  Moon,
  Network,
  Repeat2,
  Search,
  Sun,
  type LucideIcon,
} from "lucide-react";
import {
  AccountFilter,
  AccountType,
  ApiDashboardData,
  CounterpartySummary,
  CodeState,
  DashboardData,
  DashboardMetadata,
  DashboardQuery,
  RecognitionFilter,
  RecognitionStatus,
  dashboardDataMode,
  loadApiDashboardData,
  loadDashboardData,
  loadNextApiEvents,
  resetTokenRecognition,
  setTokenRecognition,
  TimelineBucket,
  TimelineInterval,
  TimelineRow,
  TokenSummary,
  WalletEvent,
} from "./data";

type Theme = "light" | "dark";
const EVENT_PAGE_SIZE = 10;
const DEFAULT_COUNTERPARTY_LIMIT = 10;
const COUNTERPARTY_LIMITS = [10, 25, 50] as const;
const ACCOUNT_FILTERS: AccountFilter[] = ["eoa_candidate", "contract"];
const RECOGNITION_FILTERS: RecognitionFilter[] = ["all", "recognized", "other"];
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

function EtherscanLink({
  href,
  title,
  children,
  className,
}: {
  href: string;
  title: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <a className={className} href={href} target="_blank" rel="noreferrer" title={title}>
      {children}
    </a>
  );
}

function InfoTooltip({
  label,
  title,
  children,
  align = "right",
}: {
  label: string;
  title: string;
  children: ReactNode;
  align?: "left" | "right";
}) {
  const tooltipId = useId();
  return (
    <span className={`infoTooltip ${align}`}>
      <button
        className="infoTooltipTrigger"
        type="button"
        aria-label={label}
        aria-describedby={tooltipId}
      >
        <Info size={15} aria-hidden="true" />
      </button>
      <span className="infoTooltipContent" id={tooltipId} role="tooltip">
        <strong>{title}</strong>
        <span>{children}</span>
      </span>
    </span>
  );
}

function shortAddress(address: string): string {
  if (address.length <= 14) {
    return address;
  }
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function compactAddress(address: string): string {
  if (address.length <= 12) {
    return address;
  }
  return `${address.slice(0, 5)}...${address.slice(-3)}`;
}

function generatedAtLabel(value: string): string {
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

type RankedCounterparty = Omit<CounterpartySummary, "token_status" | "token_quality" | "recognition_status">;
type DisplayedTokenSummary = Omit<TokenSummary, "counterparty_account_type">;
type DisplayedTimelineRow = Omit<TimelineRow, "counterparty_account_type">;

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
    existing.value_raw_sum = (BigInt(existing.value_raw_sum) + BigInt(row.value_raw_sum)).toString();
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
    existing.value_raw_sum = (BigInt(existing.value_raw_sum) + BigInt(row.value_raw_sum)).toString();
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
      const {
        token_status: _tokenStatus,
        token_quality: _tokenQuality,
        recognition_status: _recognitionStatus,
        ...summary
      } = row;
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

function Stat({ icon: Icon, label, value }: { icon: LucideIcon; label: string; value: string }) {
  return (
    <div className="stat">
      <Icon size={18} aria-hidden="true" />
      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

const ACCOUNT_LABELS: Record<AccountFilter, string> = {
  eoa_candidate: "EOA",
  contract: "Contract",
};

export function accountMatches(
  accountType: AccountType,
  selected: AccountFilter[],
): boolean {
  return selected.length === ACCOUNT_FILTERS.length || selected.some((value) => value === accountType);
}

type BadgeEvidence = {
  accountType: AccountType;
  codeState: CodeState;
  observationBlock: number | null;
  delegationTarget: string | null;
};

function AccountTypeBadge({ evidence }: { evidence: BadgeEvidence }) {
  if (evidence.accountType === "unknown") {
    return null;
  }
  const title = evidence.accountType === "eoa_candidate"
    ? evidence.codeState === "eip7702_delegated"
      ? `EOA with an exact EIP-7702 delegation indicator observed at pinned block ${evidence.observationBlock ?? "unknown"}${evidence.delegationTarget ? `; target ${evidence.delegationTarget}` : ""}`
      : `No bytecode observed at pinned block ${evidence.observationBlock ?? "unknown"}; this does not establish personhood or permanent EOA status`
    : `Contract bytecode observed at pinned block ${evidence.observationBlock ?? "unknown"}`;
  return <span className={`accountType ${evidence.accountType}`} title={title}>{ACCOUNT_LABELS[evidence.accountType]}</span>;
}

function AccountBadges({ evidence }: { evidence: BadgeEvidence }) {
  return (
    <span className="accountBadges">
      <AccountTypeBadge evidence={evidence} />
    </span>
  );
}

function summaryBadgeEvidence(row: CounterpartySummary | RankedCounterparty): BadgeEvidence {
  return {
    accountType: row.account_type,
    codeState: row.code_state,
    observationBlock: row.observation_block_number,
    delegationTarget: row.eip7702_delegation_target,
  };
}

function eventBadgeEvidence(event: WalletEvent): BadgeEvidence {
  return {
    accountType: event.counterparty_account_type,
    codeState: event.counterparty_code_state,
    observationBlock: event.counterparty_observation_block_number,
    delegationTarget: event.counterparty_eip7702_delegation_target,
  };
}

function utcDate(value: string): Date {
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

function timelinePeriodLabel(
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

function timelineTickLabel(bucket: TimelineBucket, interval: TimelineInterval): string {
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

function timelineScaleLabel(value: number, maximum: number): string {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: maximum < 100 ? 2 : 0,
  });
}

export function ActivityTimeline({
  buckets,
  interval,
  selected,
  scopeYear,
  interactive,
  onSelect,
  onClear,
  onClearScope,
  partialThrough,
}: {
  buckets: TimelineBucket[];
  interval: TimelineInterval;
  selected: { start: string; end: string } | null;
  scopeYear: number | null;
  interactive: boolean;
  onSelect: (bucket: TimelineBucket) => void;
  onClear: () => void;
  onClearScope: () => void;
  partialThrough: string | null;
}) {
  const maximum = Math.max(0, ...buckets.map((bucket) => bucket.transfer_count));
  const scaleMaximum = Math.max(1, maximum);
  const scaleTicks = timelineScaleTicks(maximum);
  const partialDate = partialThrough ? new Date(partialThrough) : null;
  const tooltipId = useId();
  const [activeBucketStart, setActiveBucketStart] = useState<string | null>(null);
  const activeBucketIndex = buckets.findIndex((bucket) => bucket.bucket_start === activeBucketStart);
  const activeBucket = activeBucketIndex >= 0 ? buckets[activeBucketIndex] : null;
  return (
    <>
      <div className="timelineToolbar">
        <div className="timelineLegend" aria-label="Timeline legend">
          <span><i className="timelineInSwatch" />Inbound</span>
          <span><i className="timelineOutSwatch" />Outbound</span>
          <span><i className="timelineSelfSwatch" />Self</span>
        </div>
      </div>
      {selected && (
        <div className="timelineSelection">
          <span>
            <CalendarDays size={15} aria-hidden="true" />
            Filtering dashboard to {timelinePeriodLabel({
              bucket_start: selected.start,
              bucket_end: selected.end,
            }, interval)} UTC
          </span>
          <button type="button" onClick={onClear}>Clear month</button>
        </div>
      )}
      {!selected && scopeYear != null && (
        <div className="timelineSelection">
          <span>
            <CalendarDays size={15} aria-hidden="true" />
            {interactive
              ? `Filtering dashboard to ${scopeYear} UTC`
              : `Showing ${scopeYear} monthly activity`}
          </span>
          <button type="button" onClick={onClearScope}>All years</button>
        </div>
      )}
      {!interactive && (
        <p className="timelineDemoNote">Period cross-filtering is available in local live mode.</p>
      )}
      <div className="timelineScroll" role="region" aria-label="Captured event activity over time" tabIndex={0}>
        {buckets.length === 0 ? (
          <div className="timelineEmpty">No timeline activity matches</div>
        ) : (
          <div className="timelineChart">
            <div className="timelineYAxisTitle">Captured events</div>
            <div className={`timelineScale${maximum === 0 ? " empty" : ""}`} aria-label="Captured event count scale">
              {scaleTicks.map((tick, index) => (
                <span key={`${tick}-${index}`}>{timelineScaleLabel(tick, maximum)}</span>
              ))}
            </div>
            <div className="timelinePlot">
              {buckets.map((bucket) => {
                const selectedPeriod = selected?.start === bucket.bucket_start && selected.end === bucket.bucket_end;
                const bucketStartDate = utcDate(bucket.bucket_start);
                const bucketEndDate = utcDate(bucket.bucket_end);
                const isPartial = partialDate != null &&
                  bucketStartDate <= partialDate &&
                  partialDate < bucketEndDate;
                const height = bucket.transfer_count === 0
                  ? 0
                  : Math.max(1.5, bucket.transfer_count / scaleMaximum * 100);
                const inboundShare = bucket.transfer_count === 0
                  ? 0
                  : bucket.inbound_transfer_count / bucket.transfer_count * 100;
                const outboundShare = bucket.transfer_count === 0
                  ? 0
                  : bucket.outbound_transfer_count / bucket.transfer_count * 100;
                const selfShare = bucket.transfer_count === 0
                  ? 0
                  : bucket.self_transfer_count / bucket.transfer_count * 100;
                const style = {
                  "--timeline-height": `${height}%`,
                  "--timeline-in-share": `${inboundShare}%`,
                  "--timeline-out-share": `${outboundShare}%`,
                  "--timeline-self-share": `${selfShare}%`,
                } as CSSProperties;
                const period = timelinePeriodLabel(bucket, interval);
                const title = `${period} UTC: ${bucket.transfer_count.toLocaleString("en-US")} captured events (${bucket.inbound_transfer_count.toLocaleString("en-US")} inbound, ${bucket.outbound_transfer_count.toLocaleString("en-US")} outbound, ${bucket.self_transfer_count.toLocaleString("en-US")} self)${isPartial ? "; partial calendar period at data generation" : ""}`;
                return (
                  <button
                    key={bucket.bucket_start}
                    type="button"
                    className={`timelineBucket${selectedPeriod ? " selected" : ""}${isPartial ? " partial" : ""}`}
                    style={style}
                    aria-label={`${title}${interactive ? interval === "year" ? ". Open this year." : ". Select this month." : ""}`}
                    aria-describedby={activeBucketStart === bucket.bucket_start ? tooltipId : undefined}
                    aria-pressed={interactive ? selectedPeriod : undefined}
                    aria-disabled={!interactive}
                    onMouseEnter={() => setActiveBucketStart(bucket.bucket_start)}
                    onMouseLeave={() => setActiveBucketStart(null)}
                    onFocus={() => setActiveBucketStart(bucket.bucket_start)}
                    onBlur={() => setActiveBucketStart(null)}
                    onClick={() => interactive && onSelect(bucket)}
                  >
                    <span className="timelineBar" aria-hidden="true">
                      <i className="timelineInSegment" />
                      <i className="timelineOutSegment" />
                      <i className="timelineSelfSegment" />
                    </span>
                    <span className="timelineTick" aria-hidden="true">
                      {timelineTickLabel(bucket, interval)}{isPartial ? "*" : ""}
                    </span>
                  </button>
                );
              })}
              {activeBucket && (
                <div
                  className="timelineHoverTooltip"
                  id={tooltipId}
                  role="tooltip"
                  style={{
                    "--timeline-tooltip-position":
                      `${(activeBucketIndex + 0.5) / buckets.length * 100}%`,
                  } as CSSProperties}
                >
                  <strong>{timelinePeriodLabel(activeBucket, interval)} UTC</strong>
                  <span>{activeBucket.transfer_count.toLocaleString("en-US")} captured events</span>
                  <span>
                    {activeBucket.inbound_transfer_count.toLocaleString("en-US")} inbound
                    {" · "}
                    {activeBucket.outbound_transfer_count.toLocaleString("en-US")} outbound
                    {" · "}
                    {activeBucket.self_transfer_count.toLocaleString("en-US")} self
                  </span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
      {partialDate && buckets.some((bucket) =>
        utcDate(bucket.bucket_start) <= partialDate && partialDate < utcDate(bucket.bucket_end)) && (
        <p className="timelinePartialNote">* Current calendar period is partial at data generation time.</p>
      )}
    </>
  );
}

export function TokenTable({
  rows,
  editable,
  updatingToken,
  onRecognitionChange,
}: {
  rows: DisplayedTokenSummary[];
  editable: boolean;
  updatingToken: string | null;
  onRecognitionChange: (row: DisplayedTokenSummary, value: RecognitionStatus | "automatic") => void;
}) {
  const rankedRows = [...rows].sort((left, right) =>
    right.transfer_count - left.transfer_count ||
    left.token_address.localeCompare(right.token_address),
  );
  const maximumTransferCount = Math.max(
    ...rankedRows.map((row) => row.transfer_count),
    0,
  );

  return (
    <table className="tokenActivityTable">
      <thead>
        <tr>
          <th>Token</th>
          <th title="Captured Transfer-signature event count">Activity</th>
          <th title="Captured Transfer-signature event counts relative to the tracked wallet">
            Direction
          </th>
          <th>Counterparties</th>
          <th aria-label="Recognition">
            <span className="tableHeaderInfo">
              Recognition
              <InfoTooltip label="How token recognition works" title="Recognition controls" align="left">
                Automatic uses the stored exact-address registry or reviewed seed result. Recognized
                and Other save a local override in this dashboard; choosing Automatic removes it.
              </InfoTooltip>
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        {rankedRows.length === 0 && (
          <tr>
            <td className="tableEmpty" colSpan={5}>No token activity matches</td>
          </tr>
        )}
        {rankedRows.map((row, index) => (
          <tr key={row.token_address}>
            <td>
              <div className="tokenIdentityCell">
                <span className="rankCell">{index + 1}</span>
                <div>
                  <div className="tokenIdentityPrimary">
                    <EtherscanLink
                      className="etherscanLink"
                      href={etherscanTokenUrl(row.token_address)}
                      title={`View ${row.token_symbol} on Etherscan`}
                    >
                      {row.token_symbol}
                    </EtherscanLink>
                    {row.token_name && <span title={row.token_name}>{row.token_name}</span>}
                  </div>
                  <EtherscanLink
                    className="tokenContractLink"
                    href={etherscanTokenUrl(row.token_address)}
                    title={`View contract ${row.token_address} on Etherscan`}
                  >
                    <code>{shortAddress(row.token_address)}</code>
                    <ExternalLink size={11} aria-hidden="true" />
                  </EtherscanLink>
                </div>
              </div>
            </td>
            <td className="tokenActivityCell">
              <strong>{row.transfer_count.toLocaleString("en-US")}</strong>
              <div
                className="tokenActivityBar"
                title={`${row.transfer_count.toLocaleString("en-US")} captured Transfer-signature events`}
              >
                <span
                  aria-hidden="true"
                  style={{
                    width: maximumTransferCount === 0
                      ? "0%"
                      : `${row.transfer_count / maximumTransferCount * 100}%`,
                  }}
                />
              </div>
            </td>
            <td className="tokenDirectionCell">
              <span className="flowIndicator">
                <span className="direction in"><ArrowDownLeft size={13} />In {row.inbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction out"><ArrowUpRight size={13} />Out {row.outbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction self"><Repeat2 size={13} />Self {(row.self_transfer_count ?? 0).toLocaleString("en-US")}</span>
              </span>
              <small title={INDIRECT_TRANSFER_EXPLANATION}>
                Indirect {row.indirect_inbound_transfer_count.toLocaleString("en-US")} in · {row.indirect_outbound_transfer_count.toLocaleString("en-US")} out
              </small>
            </td>
            <td className="tokenCounterpartyCell">
              <strong>{row.counterparty_count.toLocaleString("en-US")}</strong>
              <small
                title={`${row.sender_account_count.toLocaleString("en-US")} distinct non-zero sender accounts, ${row.recipient_account_count.toLocaleString("en-US")} distinct non-zero recipient accounts`}
              >
                {row.sender_account_count.toLocaleString("en-US")} senders · {row.recipient_account_count.toLocaleString("en-US")} recipients
              </small>
            </td>
            <td>
              <div className="recognitionCell">
                <span className={`recognitionStatus ${row.recognition_status}`}>
                  {row.recognition_status === "recognized" ? "Recognized" : "Other"}
                </span>
                <select
                  aria-label={`Recognition for ${row.token_symbol}`}
                  value={row.recognition_override_status ?? "automatic"}
                  disabled={!editable || updatingToken === row.token_address}
                  title={editable ? "Set a local recognition override" : "Manual overrides are available in live API mode"}
                  onChange={(event) => onRecognitionChange(
                    row,
                    event.target.value as RecognitionStatus | "automatic",
                  )}
                >
                  <option value="automatic">Automatic</option>
                  <option value="recognized">Recognized</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function CounterpartyTable({ rows }: { rows: RankedCounterparty[] }) {
  return (
    <table className="counterpartyTable">
      <thead>
        <tr>
          <th>#</th>
          <th>Account</th>
          <th>Activity</th>
          <th title="Captured Transfer-signature event counts relative to the tracked wallet">
            Inbound / Outbound Events
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td className="tableEmpty" colSpan={4}>No counterparties match</td>
          </tr>
        )}
        {rows.map((row, index) => (
          <tr key={row.counterparty_address}>
            <td className="rankCell">{index + 1}</td>
            <td className="accountCell">
              <div>
                <EtherscanLink
                  className="addressLink"
                  href={etherscanAddressUrl(row.counterparty_address)}
                  title={`View ${row.counterparty_address} on Etherscan`}
                >
                  <code>{compactAddress(row.counterparty_address)}</code>
                </EtherscanLink>
                <AccountBadges evidence={summaryBadgeEvidence(row)} />
              </div>
              <small>Last active {new Date(row.last_seen_at).toLocaleDateString()}</small>
            </td>
            <td className="activityCell">
              <strong>{row.transfer_count.toLocaleString("en-US")}</strong>
              <small>{row.token_count.toLocaleString("en-US")} {row.token_count === 1 ? "token" : "tokens"}</small>
            </td>
            <td>
              <span
                className="flowIndicator"
                title={`${row.inbound_transfer_count.toLocaleString("en-US")} inbound, ${row.outbound_transfer_count.toLocaleString("en-US")} outbound Transfer events`}
              >
                <span className="direction in"><ArrowDownLeft size={13} />{row.inbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction out"><ArrowUpRight size={13} />{row.outbound_transfer_count.toLocaleString("en-US")}</span>
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function EventList({
  events,
  limit,
  totalCount,
  showMoreDisabled,
  onShowMore,
  onShowLess,
}: {
  events: WalletEvent[];
  limit: number;
  totalCount: number;
  showMoreDisabled: boolean;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const visibleEvents = events.slice(0, limit);
  const canShowLess = limit > EVENT_PAGE_SIZE && events.length > EVENT_PAGE_SIZE;
  const canShowMore = visibleEvents.length < totalCount;

  return (
    <div className="events">
      {visibleEvents.length === 0 && <div className="listEmpty">No events match</div>}
      {visibleEvents.map((event) => (
        <article key={event.transfer_id} className="event">
          <div>
            <strong>
              <EtherscanLink
                className="etherscanLink"
                href={etherscanTokenUrl(event.token_address)}
                title={`View ${event.token_symbol ?? event.token_address} on Etherscan`}
              >
                {event.token_symbol ?? shortAddress(event.token_address)}
              </EtherscanLink>
            </strong>
            <span>{new Date(event.block_timestamp).toLocaleString()}</span>
            <EtherscanLink
              className="transactionLink"
              href={etherscanTransactionUrl(event.transaction_hash)}
              title="View transaction on Etherscan"
            >
              <ExternalLink size={14} aria-hidden="true" />
              <span className="srOnly">View transaction on Etherscan</span>
            </EtherscanLink>
          </div>
          <div>
            <span
              className={`direction ${event.direction}`}
              title={
                event.direction === "self"
                  ? SELF_TRANSFER_EXPLANATION
                  : event.is_indirect
                    ? INDIRECT_TRANSFER_EXPLANATION
                    : undefined
              }
            >
              {event.direction === "in"
                ? <ArrowDownLeft size={14} />
                : event.direction === "out"
                  ? <ArrowUpRight size={14} />
                  : <Repeat2 size={14} />}
              {event.direction}{event.direction !== "self" && event.is_indirect ? "*" : ""}
            </span>
            <EtherscanLink
              className="addressLink"
              href={etherscanAddressUrl(event.counterparty_address)}
              title={`View ${event.counterparty_address} on Etherscan`}
            >
              <code>{event.direction === "self" ? "same wallet" : shortAddress(event.counterparty_address)}</code>
            </EtherscanLink>
            <AccountBadges evidence={eventBadgeEvidence(event)} />
          </div>
        </article>
      ))}
      {(canShowLess || canShowMore) && (
        <div className="eventControls">
          {canShowLess && (
            <button className="eventPageButton" type="button" onClick={onShowLess}>
              <ChevronUp size={16} />
              Show less
            </button>
          )}
          {canShowMore && (
            <button className="eventPageButton" type="button" onClick={onShowMore} disabled={showMoreDisabled}>
              <ChevronDown size={16} />
              Show more
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function App() {
  const [data, setData] = useState<DashboardData<DashboardMetadata> | null>(null);
  const [apiResult, setApiResult] = useState<ApiDashboardData | null>(null);
  const [apiResultQueryKey, setApiResultQueryKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [eventLimit, setEventLimit] = useState(EVENT_PAGE_SIZE);
  const [loadingMoreEvents, setLoadingMoreEvents] = useState(false);
  const apiMetadataRef = useRef<ApiDashboardData["data"]["metadata"] | undefined>(undefined);
  const [counterpartyLimit, setCounterpartyLimit] = useState(DEFAULT_COUNTERPARTY_LIMIT);
  const [selectedYear, setSelectedYear] = useState<number | null>(null);
  const [selectedMonth, setSelectedMonth] = useState<{ start: string; end: string } | null>(null);
  const [recognitionFilter, setRecognitionFilter] = useState<RecognitionFilter>("all");
  const [dataRevision, setDataRevision] = useState(0);
  const [updatingToken, setUpdatingToken] = useState<string | null>(null);
  const [undoAction, setUndoAction] = useState<{
    tokenAddress: string;
    tokenLabel: string;
    previousOverride: RecognitionStatus | null;
  } | null>(null);
  const [recognitionActionError, setRecognitionActionError] = useState<string | null>(null);
  const undoTimerRef = useRef<number | null>(null);
  const [selectedAccountFilters, setSelectedAccountFilters] = useState<AccountFilter[]>(ACCOUNT_FILTERS);
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      return saved;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    if (dashboardDataMode !== "static") {
      return;
    }
    const controller = new AbortController();
    loadDashboardData(controller.signal).then(setData).catch((loadError: unknown) => {
      if (loadError instanceof Error && loadError.name === "AbortError") {
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Could not load dashboard data");
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const timeout = window.setTimeout(() => setDebouncedQuery(query), 200);
    return () => window.clearTimeout(timeout);
  }, [query]);

  const timelineInterval: TimelineInterval = selectedYear == null ? "year" : "month";
  const selectedPeriod = useMemo(() => {
    if (selectedMonth) {
      return selectedMonth;
    }
    if (selectedYear == null) {
      return null;
    }
    return {
      start: `${selectedYear}-01-01`,
      end: `${selectedYear + 1}-01-01`,
    };
  }, [selectedMonth, selectedYear]);

  const dashboardQuery = useMemo((): DashboardQuery => ({
    recognition: recognitionFilter,
    accountFilters: selectedAccountFilters,
    query: debouncedQuery,
    counterpartyLimit,
    timelineInterval,
    timelineYear: selectedYear,
    startDate: selectedPeriod?.start ?? null,
    endDate: selectedPeriod?.end ?? null,
  }), [
    recognitionFilter,
    selectedAccountFilters,
    debouncedQuery,
    counterpartyLimit,
    timelineInterval,
    selectedYear,
    selectedPeriod,
  ]);
  const dashboardQueryKey = JSON.stringify(dashboardQuery);
  const dashboardQueryKeyRef = useRef(dashboardQueryKey);
  const dashboardLoadGenerationRef = useRef(0);
  useEffect(() => {
    dashboardQueryKeyRef.current = dashboardQueryKey;
  }, [dashboardQueryKey]);

  useEffect(() => {
    if (dashboardDataMode !== "api") {
      return;
    }
    const controller = new AbortController();
    const requestedQueryKey = dashboardQueryKey;
    const requestedGeneration = ++dashboardLoadGenerationRef.current;
    setError(null);
    setLoadingMoreEvents(false);
    loadApiDashboardData(dashboardQuery, controller.signal, apiMetadataRef.current).then((result) => {
      if (
        dashboardQueryKeyRef.current !== requestedQueryKey ||
        dashboardLoadGenerationRef.current !== requestedGeneration
      ) {
        return;
      }
      apiMetadataRef.current = result.data.metadata;
      setApiResult(result);
      setApiResultQueryKey(requestedQueryKey);
      setData(result.data);
    }).catch((loadError: unknown) => {
      if (loadError instanceof Error && loadError.name === "AbortError") {
        return;
      }
      if (dashboardLoadGenerationRef.current !== requestedGeneration) {
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Could not load live dashboard data");
    });
    return () => controller.abort();
  }, [dashboardQuery, dashboardQueryKey, dataRevision]);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(
    () => setEventLimit(EVENT_PAGE_SIZE),
    [debouncedQuery, recognitionFilter, selectedAccountFilters, selectedPeriod],
  );
  useEffect(
    () => setCounterpartyLimit(DEFAULT_COUNTERPARTY_LIMIT),
    [debouncedQuery, recognitionFilter, selectedAccountFilters, selectedPeriod],
  );

  useEffect(() => () => {
    if (undoTimerRef.current != null) {
      window.clearTimeout(undoTimerRef.current);
    }
  }, []);

  const filtered = useMemo(() => {
    if (!data) {
      return null;
    }
    if (dashboardDataMode === "api") {
      return data;
    }

    const recognitionVisible = (status: RecognitionStatus) =>
      recognitionFilter === "all" || recognitionFilter === status;
    const accountVisible = (accountType: AccountType) => accountMatches(accountType, selectedAccountFilters);
    const visibleEvents = data.events.filter((event) =>
      recognitionVisible(event.recognition_status) &&
      accountVisible(event.counterparty_account_type));
    const visibleTokens = data.summaries.tokens.filter((row) =>
      recognitionVisible(row.recognition_status) &&
      accountVisible(row.counterparty_account_type));
    const visibleCounterparties = data.summaries.counterparties.filter((row) =>
      recognitionVisible(row.recognition_status) &&
      accountVisible(row.account_type));
    const visibleTimeline = data.timeline.filter((row) =>
      recognitionVisible(row.recognition_status) &&
      accountVisible(row.counterparty_account_type));
    const visibleData = {
      ...data,
      events: visibleEvents,
      summaries: { tokens: aggregateTokenSummaries(visibleTokens), counterparties: visibleCounterparties },
      timeline: aggregateTimelineRows(visibleTimeline),
    };

    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return visibleData;
    }

    const eventMatches = (event: WalletEvent) =>
      [
        event.transfer_id,
        event.transaction_hash,
        event.transaction_from_address,
        event.transaction_to_address,
        event.block_date,
        event.direction,
        event.transaction_sender_relation,
        event.transaction_target_relation,
        event.wallet_address,
        event.counterparty_address,
        event.counterparty_account_type,
        event.counterparty_code_state,
        event.counterparty_evidence_reason_codes,
        event.token_address,
        event.token_symbol,
        event.token_name,
        event.recognition_status,
        event.recognition_source,
        event.metadata_availability,
        event.metadata_source,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));

    const tokenMatches = (row: DisplayedTokenSummary) =>
      [row.token_symbol, row.token_name, row.token_address, row.recognition_status,
        row.recognition_source, row.metadata_source, row.metadata_availability]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));

    const events = visibleData.events.filter(eventMatches);
    const directlyMatchedTokens = visibleData.summaries.tokens.filter(tokenMatches);
    const directlyMatchedCounterparties = visibleData.summaries.counterparties.filter((row) =>
      [row.counterparty_address, row.account_type, row.code_state, row.evidence_reason_codes]
        .some((value) => String(value).toLowerCase().includes(normalizedQuery)),
    );

    const tokenAddresses = new Set([
      ...events.map((event) => event.token_address),
      ...directlyMatchedTokens.map((row) => row.token_address),
    ]);
    const counterpartyAddresses = new Set([
      ...events.map((event) => event.counterparty_address),
      ...directlyMatchedCounterparties.map((row) => row.counterparty_address),
    ]);
    const tokens = visibleData.summaries.tokens.filter(
      (row) => tokenAddresses.has(row.token_address) || tokenMatches(row),
    );
    const counterparties = visibleData.summaries.counterparties.filter(
      (row) => counterpartyAddresses.has(row.counterparty_address),
    );

    return {
      ...visibleData,
      events,
      summaries: { tokens, counterparties },
      timeline: visibleData.timeline.filter(
        (row) =>
          tokenAddresses.has(row.token_address) ||
          [row.block_date, row.direction, row.token_address, row.token_symbol]
            .some((value) => String(value).toLowerCase().includes(normalizedQuery)),
      ),
    };
  }, [data, query, recognitionFilter, selectedAccountFilters]);

  const rankedCounterparties = useMemo(
    () => filtered ? aggregateCounterparties(filtered.summaries.counterparties) : [],
    [filtered],
  );

  const stats = useMemo(() => {
    if (!filtered || !data) {
      return null;
    }
    if (dashboardDataMode === "api") {
      return apiResult ? {
        transferCount: apiResult.summary.transfer_count,
        tokenCount: apiResult.summary.token_count,
        counterpartyCount: apiResult.summary.counterparty_count,
      } : null;
    }
    const transferCount = filtered.events.length;
    const tokenCount = new Set(filtered.events.map((event) => event.token_address)).size;
    const counterpartyCount = new Set(
      filtered.events
        .filter((event) => event.counterparty_address !== event.wallet_address)
        .map((event) => event.counterparty_address),
    ).size;
    return { transferCount, tokenCount, counterpartyCount };
  }, [apiResult, data, filtered]);

  const timelineBuckets = useMemo(
    () => dashboardDataMode === "api"
      ? (apiResult?.timelineBuckets ?? [])
      : bucketTimelineRows(
        filtered?.timeline ?? [],
        timelineInterval,
        selectedYear,
        timelineYears(data?.metadata.first_event_at ?? null, data?.metadata.last_event_at ?? null),
      ),
    [apiResult, data, filtered, selectedYear, timelineInterval],
  );
  const availableTimelineYears = useMemo(
    () => timelineYears(data?.metadata.first_event_at ?? null, data?.metadata.last_event_at ?? null),
    [data],
  );

  const eventCount = dashboardDataMode === "api"
    ? (apiResult?.eventCount ?? 0)
    : (filtered?.events.length ?? 0);
  const tokenCount = dashboardDataMode === "api"
    ? (apiResult?.tokenCount ?? 0)
    : (filtered?.summaries.tokens.length ?? 0);
  const apiResultIsCurrent = dashboardDataMode !== "api" || apiResultQueryKey === dashboardQueryKey;

  function changeTimelineYear(value: number | null) {
    setSelectedYear(value);
    setSelectedMonth(null);
  }

  function selectTimelineBucket(bucket: TimelineBucket) {
    if (timelineInterval === "year") {
      changeTimelineYear(utcDate(bucket.bucket_start).getUTCFullYear());
      return;
    }
    setSelectedMonth((current) =>
      current?.start === bucket.bucket_start && current.end === bucket.bucket_end
        ? null
        : { start: bucket.bucket_start, end: bucket.bucket_end });
  }

  async function showMoreEvents() {
    if (!data || loadingMoreEvents || !apiResultIsCurrent) {
      return;
    }
    if (eventLimit < data.events.length) {
      setEventLimit((current) => current + EVENT_PAGE_SIZE);
      return;
    }
    if (dashboardDataMode !== "api" || !apiResult?.eventNextCursor) {
      setEventLimit((current) => current + EVENT_PAGE_SIZE);
      return;
    }

    setLoadingMoreEvents(true);
    const requestedQueryKey = dashboardQueryKey;
    try {
      const page = await loadNextApiEvents(dashboardQuery, apiResult.eventNextCursor);
      if (dashboardQueryKeyRef.current !== requestedQueryKey) {
        return;
      }
      setData((current) => current ? { ...current, events: [...current.events, ...page.items] } : current);
      setApiResult((current) => current ? {
        ...current,
        eventCount: page.complete_matching_count,
        eventNextCursor: page.next_cursor ?? null,
      } : current);
      setEventLimit((current) => current + EVENT_PAGE_SIZE);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load more events");
    } finally {
      if (dashboardQueryKeyRef.current === requestedQueryKey) {
        setLoadingMoreEvents(false);
      }
    }
  }

  function startUndoWindow(action: NonNullable<typeof undoAction>) {
    if (undoTimerRef.current != null) {
      window.clearTimeout(undoTimerRef.current);
    }
    setUndoAction(action);
    undoTimerRef.current = window.setTimeout(() => {
      setUndoAction(null);
      undoTimerRef.current = null;
    }, 4000);
  }

  async function changeTokenRecognition(
    row: DisplayedTokenSummary,
    nextStatus: RecognitionStatus | "automatic",
  ) {
    if (dashboardDataMode !== "api") {
      return;
    }
    setUpdatingToken(row.token_address);
    setRecognitionActionError(null);
    try {
      const result = nextStatus === "automatic"
        ? await resetTokenRecognition(row.token_address)
        : await setTokenRecognition(row.token_address, nextStatus);
      startUndoWindow({
        tokenAddress: row.token_address,
        tokenLabel: row.token_symbol,
        previousOverride: result.previous_override_status,
      });
      setDataRevision((current) => current + 1);
    } catch (actionError) {
      setRecognitionActionError(
        actionError instanceof Error ? actionError.message : "Could not update token recognition",
      );
    } finally {
      setUpdatingToken(null);
    }
  }

  async function undoTokenRecognition() {
    if (!undoAction || updatingToken) {
      return;
    }
    if (undoTimerRef.current != null) {
      window.clearTimeout(undoTimerRef.current);
      undoTimerRef.current = null;
    }
    const action = undoAction;
    setUndoAction(null);
    setUpdatingToken(action.tokenAddress);
    setRecognitionActionError(null);
    try {
      if (action.previousOverride == null) {
        await resetTokenRecognition(action.tokenAddress);
      } else {
        await setTokenRecognition(action.tokenAddress, action.previousOverride);
      }
      setDataRevision((current) => current + 1);
    } catch (actionError) {
      setRecognitionActionError(
        actionError instanceof Error ? actionError.message : "Could not undo token recognition",
      );
    } finally {
      setUpdatingToken(null);
    }
  }

  if (error) {
    return (
      <main className="shell">
        <section className="empty">
          <Database size={28} />
          <h1>EVM Wallet Search</h1>
          <p>
            {error}. {dashboardDataMode === "api"
              ? "Build live analytics, then run `bun run api:dev`."
              : "Run `bun run analytics:build` and `bun run export:dashboard`."}
          </p>
        </section>
      </main>
    );
  }

  if (!data || !stats || !filtered) {
    return (
      <main className="shell">
        <section className="empty">
          <Activity size={28} />
          <h1>EVM Wallet Search</h1>
          <p>Loading wallet analytics.</p>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <header className="topbar">
        <div className="productIdentity">
          <h1>EVM Wallet Search</h1>
          <p>
            Transfer Event Analytics based on emitted
            {" Transfer(address,address,uint256) "}events.
          </p>
        </div>
        <div className="toolbar">
          <div className="recognitionControls">
            <fieldset className="recognitionFilter">
              <legend className="srOnly">Token recognition</legend>
              {RECOGNITION_FILTERS.map((value) => (
                <label key={value}>
                  <input
                    type="radio"
                    name="recognition-filter"
                    value={value}
                    checked={recognitionFilter === value}
                    onChange={() => setRecognitionFilter(value)}
                  />
                  <span>{value === "all" ? "All" : value === "recognized" ? "Recognized" : "Other"}</span>
                </label>
              ))}
            </fieldset>
            <InfoTooltip label="What recognized means" title="Recognized tokens">
              The token&apos;s exact Ethereum contract address appears in Uniswap, CoinGecko,
              Trust Wallet, or qualifying Coinbase Exchange data, or was manually marked as recognized.
              Registry inclusion changes over time and does not prove safety, legitimacy, value,
              or standards compliance.
            </InfoTooltip>
          </div>
          <div className="addressTypeControls">
            <details
              className="statusFilter accountFilter"
              onMouseLeave={(event) => event.currentTarget.removeAttribute("open")}
            >
              <summary title="Filter every view by the address type observed at the pinned block">
                Address type ({selectedAccountFilters.length})
                <ChevronDown size={14} aria-hidden="true" />
              </summary>
              <div className="statusMenu accountMenu" role="group" aria-label="Address type filter">
                {ACCOUNT_FILTERS.map((accountType) => (
                  <label key={accountType}>
                    <input
                      type="checkbox"
                      checked={selectedAccountFilters.includes(accountType)}
                      onChange={(event) => setSelectedAccountFilters((current) => event.target.checked
                        ? [...current.filter((value) => value !== accountType), accountType]
                        : current.filter((value) => value !== accountType))}
                    />
                    <span className={`accountType ${accountType}`}>{ACCOUNT_LABELS[accountType]}</span>
                  </label>
                ))}
                <small>Applies to every view. Unclassified addresses remain included only when both options are selected.</small>
              </div>
            </details>
            <InfoTooltip label="How address type works" title="Address type">
              EOA means no contract bytecode was observed at the pinned block; Contract means bytecode
              was observed. This is a point-in-time classification, not proof of ownership, personhood,
              or permanent account type. Unclassified addresses appear when both options are selected.
            </InfoTooltip>
          </div>
          <label className="searchbox">
            <Search size={16} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter token, address, tx"
              aria-label="Filter dashboard"
            />
          </label>
          <button
            className="iconButton"
            type="button"
            onClick={() => setTheme((current) => (current === "light" ? "dark" : "light"))}
            aria-label={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
            title={`Switch to ${theme === "light" ? "dark" : "light"} theme`}
          >
            {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
          </button>
        </div>
      </header>

      <section className="overviewContext" aria-label="Analysis context">
        <div className="analysisSubject">
          <span className="contextLabel">Analyzing</span>
          <div className="subjectIdentity">
            <EtherscanLink
              className="subjectAddress"
              href={etherscanAddressUrl(data.metadata.wallet_address)}
              title="View analyzed address on Etherscan"
            >
              <code>{compactAddress(data.metadata.wallet_address)}</code>
              <ExternalLink size={13} aria-hidden="true" />
            </EtherscanLink>
            <span
              className="subjectLabel"
              title="Configured project label; not a live ENS resolution."
            >
              {data.metadata.ens}
            </span>
          </div>
          <div className="subjectMeta">
            <span>Ethereum mainnet</span>
            <span className={`sourceBadge ${data.metadata.data_source}`}>
              {data.metadata.data_source === "fixture" ? "Example wallet" : "Configured wallet"}
            </span>
          </div>
        </div>
        <div className={`selectionContext ${data.metadata.data_source}`}>
          <strong>Current selection</strong>
          <span>{data.metadata.data_source === "fixture" ? "Fixture data" : "HyperIndex data"}</span>
          <span>{snapshotCoverageLabel(data.metadata)}</span>
          <span>Generated {generatedAtLabel(data.metadata.generated_at)}</span>
          <span title={accountEvidenceCoverageDescription(data.metadata)}>
            {accountEvidenceCoverageLabel(data.metadata)} · {accountEvidenceObservationBlockLabel(data.metadata.account_evidence_observation_block_number_min, data.metadata.account_evidence_observation_block_number_max)}
          </span>
          {data.metadata.is_sampled && "exported_event_count" in data.metadata && (
            <span>{data.metadata.exported_event_count.toLocaleString()} recent events shown</span>
          )}
        </div>
      </section>

      <section className="stats" aria-label="Current selection summary">
        <Stat icon={Activity} label="Transfers" value={stats.transferCount.toString()} />
        <Stat icon={Database} label="Tokens" value={stats.tokenCount.toString()} />
        <Stat icon={Network} label="Counterparties" value={stats.counterpartyCount.toString()} />
      </section>

      <section className="workspace">
        <div className="panel timelinePanel">
          <div className="panelHeader">
            <div className="panelTitle">
              <h2>Activity Timeline</h2>
              <p>
                {selectedYear == null
                  ? "Yearly captured Transfer-signature event overview in UTC."
                  : `Monthly captured Transfer-signature events for ${selectedYear} in UTC.`}
              </p>
            </div>
            <label className="panelSelect">
              <span>Year</span>
              <select
                aria-label="Timeline year"
                value={selectedYear ?? ""}
                onChange={(event) =>
                  changeTimelineYear(event.target.value ? Number(event.target.value) : null)}
              >
                <option value="">All years</option>
                {availableTimelineYears.map((year) => (
                  <option key={year} value={year}>{year}</option>
                ))}
              </select>
            </label>
          </div>
          <ActivityTimeline
            buckets={timelineBuckets}
            interval={timelineInterval}
            selected={selectedMonth}
            scopeYear={selectedYear}
            interactive={dashboardDataMode === "api"}
            onSelect={selectTimelineBucket}
            onClear={() => setSelectedMonth(null)}
            onClearScope={() => changeTimelineYear(null)}
            partialThrough={dashboardDataMode === "api" ? data.metadata.generated_at : null}
          />
        </div>

        <div className="panel counterpartyPanel">
          <div className="panelHeader">
            <div className="panelTitle">
              <h2>Top Counterparties</h2>
              <p>Addresses opposite the tracked wallet in Transfer events; mint/burn, self, and token contracts excluded.</p>
            </div>
            <label className="panelSelect">
              <span>Top</span>
              <select
                aria-label="Maximum counterparties"
                value={counterpartyLimit}
                onChange={(event) => setCounterpartyLimit(Number(event.target.value))}
              >
                {COUNTERPARTY_LIMITS.map((limit) => (
                  <option key={limit} value={limit}>{limit}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="counterpartyTableScroll">
            <CounterpartyTable rows={rankedCounterparties.slice(0, counterpartyLimit)} />
          </div>
          {dashboardDataMode === "api" && apiResult && (
            <p className="boundedNote">
              Showing {Math.min(counterpartyLimit, rankedCounterparties.length).toLocaleString("en-US")} of {apiResult.counterpartyCount.toLocaleString("en-US")} matching counterparties.
            </p>
          )}
        </div>

        <div className="panel tokenActivityPanel">
          <div className="panelHeader">
            <div className="panelTitle">
              <h2>Token Activity</h2>
              <p>One row per emitting contract across captured Transfer-signature events.</p>
            </div>
            <span>
              {filtered.summaries.tokens.length === tokenCount
                ? `${tokenCount.toLocaleString("en-US")} tokens`
                : `${filtered.summaries.tokens.length.toLocaleString("en-US")} of ${tokenCount.toLocaleString("en-US")} tokens`}
            </span>
          </div>
          <div className="tokenTableScroll compact">
            <TokenTable
              rows={filtered.summaries.tokens}
              editable={dashboardDataMode === "api"}
              updatingToken={updatingToken}
              onRecognitionChange={changeTokenRecognition}
            />
          </div>
        </div>
      </section>

      <section className="panel">
          <div className="panelHeader">
            <h2>Recent Events</h2>
            <span>
              {Math.min(eventLimit, filtered.events.length)} of {eventCount.toLocaleString("en-US")} events
            </span>
          </div>
        <EventList
          events={filtered.events}
          limit={eventLimit}
          totalCount={eventCount}
          showMoreDisabled={loadingMoreEvents || !apiResultIsCurrent}
          onShowMore={showMoreEvents}
          onShowLess={() => setEventLimit((current) => Math.max(EVENT_PAGE_SIZE, current - EVENT_PAGE_SIZE))}
        />
      </section>

      {(undoAction || recognitionActionError) && (
        <div className="recognitionToast" role="status" aria-live="polite">
          <span>
            {recognitionActionError ?? `Updated recognition for ${undoAction?.tokenLabel}.`}
          </span>
          {undoAction && !recognitionActionError && (
            <button type="button" onClick={undoTokenRecognition} disabled={updatingToken != null}>Undo</button>
          )}
        </div>
      )}
    </main>
  );
}
