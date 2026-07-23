import { useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import cytoscape from "cytoscape";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Database,
  ExternalLink,
  Info,
  Maximize2,
  Minimize2,
  Moon,
  Network,
  RotateCcw,
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
  DashboardGraph,
  DashboardMetadata,
  DashboardQuery,
  GraphEdge,
  RecognitionFilter,
  RecognitionStatus,
  dashboardDataMode,
  loadApiDashboardData,
  loadDashboardData,
  loadNextApiEvents,
  resetTokenRecognition,
  setTokenRecognition,
  TimelineRow,
  TokenSummary,
  WalletEvent,
} from "./data";

type Theme = "light" | "dark";
const EVENT_PAGE_SIZE = 10;
const DEFAULT_GRAPH_INTERACTION_LIMIT = 25;
const GRAPH_INTERACTION_LIMITS = [10, 25, 50, 100] as const;
const DEFAULT_COUNTERPARTY_LIMIT = 10;
const COUNTERPARTY_LIMITS = [10, 25, 50] as const;
const ACCOUNT_FILTERS: AccountFilter[] = ["eoa_candidate", "contract"];
const RECOGNITION_FILTERS: RecognitionFilter[] = ["all", "recognized", "other"];
const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";
const ETHERSCAN_BASE_URL = "https://etherscan.io";
export const INDIRECT_TRANSFER_EXPLANATION = "Top-level transaction sender differs from Transfer.from. This can happen with transferFrom, routers, Safe/account abstraction, or synthetic event emission; the mismatch alone does not prove intent or legitimacy.";

export function etherscanAddressUrl(address: string): string {
  return `${ETHERSCAN_BASE_URL}/address/${address}`;
}

export function etherscanTokenUrl(address: string): string {
  return `${ETHERSCAN_BASE_URL}/token/${address}`;
}

export function etherscanTransactionUrl(hash: string): string {
  return `${ETHERSCAN_BASE_URL}/tx/${hash}`;
}

export function etherscanInteractionUrl(walletAddress: string, counterpartyAddress: string): string {
  const parameters = new URLSearchParams();
  parameters.set("txntype", "2");
  parameters.append("fadd", walletAddress);
  parameters.append("fadd", counterpartyAddress);
  parameters.append("tadd", walletAddress);
  parameters.append("tadd", counterpartyAddress);
  parameters.set("qt", "1");
  return `${ETHERSCAN_BASE_URL}/advanced-filter?${parameters.toString()}`;
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

function openEtherscan(url: string) {
  const opened = window.open(url, "_blank", "noopener,noreferrer");
  if (opened) {
    opened.opener = null;
  }
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
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function compactAddress(address: string): string {
  return `${address.slice(0, 5)}...${address.slice(-3)}`;
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
    const key = [row.wallet_id, row.block_date, row.token_address, row.recognition_status, row.direction].join("|");
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

export function counterpartyNodeSize(transferCount: number): number {
  const ratio = Math.log10(Math.max(1, transferCount)) / 4;
  return Math.round(26 + Math.max(0, Math.min(1, ratio)) * 42);
}

export function interactionEdgeLabel(transferCount: number): string {
  return `${transferCount.toLocaleString("en-US")} ${transferCount === 1 ? "transfer" : "transfers"}`;
}

export function buildCounterpartyGraph(
  data: {
    graph: DashboardGraph;
    summaries: { counterparties: CounterpartySummary[] };
  },
  limit: number,
): DashboardGraph {
  const rankedSummaries = aggregateCounterparties(data.summaries.counterparties);
  const counterpartyCounts = new Map(
    rankedSummaries.map((row) => [row.counterparty_address, row.transfer_count]),
  );
  const representatives = new Map<string, GraphEdge>();

  for (const edge of data.graph.edges) {
    if (
      edge.data.counterpartyAddress !== ZERO_ADDRESS &&
      counterpartyCounts.has(edge.data.counterpartyAddress) &&
      !representatives.has(edge.data.counterpartyAddress)
    ) {
      representatives.set(edge.data.counterpartyAddress, edge);
    }
  }

  const rankedCounterparties = rankedSummaries
    .map((row) => [row.counterparty_address, representatives.get(row.counterparty_address)] as const)
    .filter((entry): entry is readonly [string, GraphEdge] => entry[1] != null)
    .slice(0, limit);

  const edges = rankedCounterparties.map(([counterpartyAddress, edge]): GraphEdge => {
    const transferCount = counterpartyCounts.get(counterpartyAddress) ?? 0;
    const walletNodeId = `wallet:${edge.data.walletAddress}`;
    const counterpartyNodeId = `counterparty:${counterpartyAddress}`;
    return {
      data: {
        ...edge.data,
        id: `counterparty:${edge.data.walletAddress}:${counterpartyAddress}:edge`,
        interactionId: `counterparty:${edge.data.walletAddress}:${counterpartyAddress}`,
        label: interactionEdgeLabel(transferCount),
        edgeRole: "wallet_counterparty",
        source: walletNodeId,
        target: counterpartyNodeId,
        direction: "both",
        tokenAddress: null,
        tokenSymbol: null,
        transferCount,
        counterpartyTransferCount: transferCount,
      },
    };
  });
  const nodeIds = new Set(edges.flatMap((edge) => [edge.data.source, edge.data.target]));
  const nodes = data.graph.nodes
    .filter((node) => node.data.type !== "token" && nodeIds.has(node.data.id))
    .map((node) => {
      if (node.data.type === "wallet") {
        return { data: { ...node.data, size: 44 } };
      }
      const transferCount = counterpartyCounts.get(node.data.address ?? "") ?? 1;
      return {
        data: {
          ...node.data,
          size: counterpartyNodeSize(transferCount),
          transferCount,
        },
      };
    });
  return { nodes, edges };
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

export function graphStyles(container: HTMLElement): cytoscape.StylesheetJson {
  const styles = getComputedStyle(container);
  const nodeText = styles.getPropertyValue("--graph-label").trim();
  const edgeColor = styles.getPropertyValue("--graph-edge").trim();
  const counterpartyColor = styles.getPropertyValue("--graph-counterparty").trim();
  const unknownColor = styles.getPropertyValue("--graph-unknown").trim();
  const walletColor = styles.getPropertyValue("--graph-wallet").trim();
  const nodeBorder = styles.getPropertyValue("--graph-node-border").trim();
  const nodeOutline = styles.getPropertyValue("--graph-label-outline").trim();
  const edgeLabelBackground = styles.getPropertyValue("--graph-edge-label-bg").trim();

  return [
    {
      selector: "node",
      style: {
        "background-color": counterpartyColor,
        "border-color": nodeBorder,
        "border-width": 1.5,
        color: nodeText,
        label: "data(label)",
        "font-family": "SFMono-Regular, Consolas, Liberation Mono, monospace",
        "font-size": 10,
        "font-weight": 500,
        "text-outline-color": nodeOutline,
        "text-outline-width": 2,
        "text-wrap": "wrap",
        "text-max-width": "110px",
        "text-valign": "bottom",
        "text-margin-y": 8,
        width: "data(size)",
        height: "data(size)",
      },
    },
    {
      selector: 'node[type = "wallet"]',
      style: { "background-color": walletColor, width: 44, height: 44, "border-width": 2 },
    },
    {
      selector: 'node[accountType = "contract"]',
      style: { shape: "round-rectangle" },
    },
    {
      selector: 'node[accountType = "unknown"]',
      style: { "background-color": unknownColor, "border-style": "solid" },
    },
    {
      selector: "edge",
      style: {
        width: "mapData(transferCount, 1, 10000, 0.8, 3.2)",
        "line-color": edgeColor,
        "target-arrow-shape": "none",
        opacity: 0.58,
        "curve-style": "straight",
        color: nodeText,
        label: "data(label)",
        "font-family": "SFMono-Regular, Consolas, Liberation Mono, monospace",
        "font-size": 9,
        "font-weight": 600,
        "text-background-color": edgeLabelBackground,
        "text-background-opacity": 0.88,
        "text-background-padding": "3px",
        "text-rotation": "autorotate",
      },
    },
    {
      selector: ".dimmed",
      style: { opacity: 0.08, "text-opacity": 0.08 },
    },
    {
      selector: "node.focused",
      style: { opacity: 1, "text-opacity": 1, "border-width": 3, "z-index": 10 },
    },
    {
      selector: "edge.focused",
      style: { opacity: 1, "z-index": 9 },
    },
  ];
}

function Graph({ data, theme, theaterMode }: { data: DashboardGraph; theme: Theme; theaterMode: boolean }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const isClampingRef = useRef(false);

  function fitGraph() {
    const cy = cyRef.current;
    if (!cy || cy.nodes().length === 0) {
      return;
    }

    // Clear the previous adaptive bounds before fitting a newly sized viewport.
    cy.minZoom(0.01);
    cy.maxZoom(10);
    cy.fit(undefined, 36);
    setAdaptiveZoomBounds(cy);
    clampPan(cy);
  }

  function clampPan(cy: cytoscape.Core) {
    if (isClampingRef.current || cy.nodes().length === 0) {
      return;
    }

    const box = cy.elements().renderedBoundingBox({ includeLabels: true });
    const container = cy.container();
    const width = container?.clientWidth ?? 0;
    const height = container?.clientHeight ?? 0;
    const margin = Math.min(140, Math.max(72, Math.min(width, height) * 0.18));
    const pan = cy.pan();
    const nextPan = { ...pan };

    if (box.w <= width - margin * 2) {
      const graphCenter = box.x1 + box.w / 2;
      const viewportCenter = width / 2;
      const maxOffset = Math.max(56, width * 0.18);
      const offset = graphCenter - viewportCenter;
      if (offset > maxOffset) nextPan.x -= offset - maxOffset;
      if (offset < -maxOffset) nextPan.x -= offset + maxOffset;
    } else if (box.x2 < margin) {
      nextPan.x += margin - box.x2;
    } else if (box.x1 > width - margin) {
      nextPan.x -= box.x1 - (width - margin);
    }

    if (box.h <= height - margin * 2) {
      const graphCenter = box.y1 + box.h / 2;
      const viewportCenter = height / 2;
      const maxOffset = Math.max(56, height * 0.18);
      const offset = graphCenter - viewportCenter;
      if (offset > maxOffset) nextPan.y -= offset - maxOffset;
      if (offset < -maxOffset) nextPan.y -= offset + maxOffset;
    } else if (box.y2 < margin) {
      nextPan.y += margin - box.y2;
    } else if (box.y1 > height - margin) {
      nextPan.y -= box.y1 - (height - margin);
    }

    if (nextPan.x !== pan.x || nextPan.y !== pan.y) {
      isClampingRef.current = true;
      cy.pan(nextPan);
      isClampingRef.current = false;
    }
  }

  function setAdaptiveZoomBounds(cy: cytoscape.Core) {
    const fitZoom = cy.zoom();
    const minZoom = Math.max(0.04, fitZoom * 0.45);
    const maxZoom = Math.min(5, Math.max(1.25, fitZoom * 4));
    cy.minZoom(minZoom);
    cy.maxZoom(maxZoom);
  }

  useEffect(() => {
    // jsdom has no real canvas or layout engine; production still initializes Cytoscape.
    if (import.meta.env.MODE === "test") {
      return;
    }

    if (!containerRef.current) {
      return;
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...data.nodes, ...data.edges],
      minZoom: 0.05,
      maxZoom: 5,
      wheelSensitivity: 0.18,
      style: graphStyles(containerRef.current),
      layout: {
        name: "concentric",
        animate: false,
        fit: true,
        padding: 42,
        avoidOverlap: true,
        minNodeSpacing: 28,
        concentric: (node) => node.data("type") === "wallet" ? 2 : 1,
        levelWidth: () => 1,
      },
    });
    cyRef.current = cy;
    const fitFrame = window.requestAnimationFrame(fitGraph);
    cy.on("pan zoom resize", () => clampPan(cy));

    const clearFocus = () => {
      cy.elements().removeClass("dimmed focused");
      const container = cy.container();
      if (container) container.style.cursor = "default";
    };
    cy.on("mouseover", "node", (event) => {
      const container = cy.container();
      if (container) container.style.cursor = "pointer";
      cy.elements().addClass("dimmed");
      event.target.closedNeighborhood().removeClass("dimmed");
      event.target.addClass("focused");
      event.target.connectedEdges().addClass("focused");
    });
    cy.on("mouseout", "node", clearFocus);
    cy.on("mouseover", "edge", (event) => {
      const container = cy.container();
      if (container) container.style.cursor = "pointer";
      const interactionId = event.target.data("interactionId");
      const interactionEdges = cy.edges().filter((edge) => edge.data("interactionId") === interactionId);
      cy.elements().addClass("dimmed");
      interactionEdges.removeClass("dimmed").addClass("focused");
      interactionEdges.connectedNodes().removeClass("dimmed");
    });
    cy.on("mouseout", "edge", clearFocus);
    cy.on("tap", "node", (event) => {
      const address = event.target.data("address");
      if (address) {
        openEtherscan(etherscanAddressUrl(address));
      }
    });
    cy.on("tap", "edge", (event) => {
      const walletAddress = event.target.data("walletAddress");
      const counterpartyAddress = event.target.data("counterpartyAddress");
      if (walletAddress && counterpartyAddress) {
        openEtherscan(etherscanInteractionUrl(walletAddress, counterpartyAddress));
      }
    });

    return () => {
      window.cancelAnimationFrame(fitFrame);
      cyRef.current = null;
      cy.destroy();
    };
  }, [data]);

  useEffect(() => {
    const cy = cyRef.current;
    const container = containerRef.current;
    if (!cy || !container) {
      return;
    }

    // Updating the stylesheet preserves node positions, pan, and zoom.
    cy.style(graphStyles(container));
  }, [theme]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) {
      return;
    }

    const resizeFrame = window.requestAnimationFrame(() => {
      cy.resize();
      fitGraph();
    });
    return () => window.cancelAnimationFrame(resizeFrame);
  }, [theaterMode]);

  return (
    <div className="graphShell" data-graph-theme={theme}>
      <button className="iconButton graphReset" type="button" onClick={fitGraph} aria-label="Reset graph view" title="Reset graph view">
        <RotateCcw size={16} />
      </button>
      <div
        className="graph"
        ref={containerRef}
        role="img"
        aria-label={`Wallet counterparty graph with ${data.nodes.length} nodes and ${data.edges.length} edges`}
      />
      {data.nodes.length === 0 && <div className="graphEmpty">No graph matches</div>}
      <div className="graphLegend" aria-label="Graph legend">
        <span><i className="walletSwatch" />Tracked address</span>
        <span><i className="counterpartySwatch" />EOA</span>
        <span><i className="contractSwatch" />Contract</span>
        <span><i className="unknownSwatch" />Unclassified</span>
      </div>
    </div>
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
  return (
    <table>
      <thead>
        <tr>
          <th>Token</th>
          <th aria-label="Recognition">
            <span className="tableHeaderInfo">
              Recognition
              <InfoTooltip label="How token recognition works" title="Recognition controls" align="left">
                Automatic uses the stored exact-address registry or reviewed seed result. Recognized
                and Other save a local override in this dashboard; choosing Automatic removes it.
              </InfoTooltip>
            </span>
          </th>
          <th>Transfers</th>
          <th>Indirect In / Out</th>
          <th>Senders | Recipients</th>
          <th>Counterparties</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td className="tableEmpty" colSpan={6}>No token flows match</td>
          </tr>
        )}
        {rows.map((row) => (
          <tr key={row.token_address}>
            <td>
              <EtherscanLink
                className="etherscanLink"
                href={etherscanTokenUrl(row.token_address)}
                title={`View ${row.token_symbol} on Etherscan`}
              >
                {row.token_symbol}
              </EtherscanLink>
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
            <td>{row.transfer_count.toLocaleString("en-US")}</td>
            <td>
              <span className="flowIndicator" title={INDIRECT_TRANSFER_EXPLANATION}>
                <span className="direction in"><ArrowDownLeft size={13} />in* {row.indirect_inbound_transfer_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction out"><ArrowUpRight size={13} />out* {row.indirect_outbound_transfer_count.toLocaleString("en-US")}</span>
              </span>
            </td>
            <td>
              <span
                className="flowIndicator"
                title={`${row.sender_account_count.toLocaleString("en-US")} distinct non-zero sender accounts, ${row.recipient_account_count.toLocaleString("en-US")} distinct non-zero recipient accounts`}
              >
                <span className="direction in"><ArrowDownLeft size={13} />{row.sender_account_count.toLocaleString("en-US")}</span>
                <i aria-hidden="true">|</i>
                <span className="direction out"><ArrowUpRight size={13} />{row.recipient_account_count.toLocaleString("en-US")}</span>
              </span>
            </td>
            <td>{row.counterparty_count.toLocaleString("en-US")}</td>
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
          <th title="ERC-20 transfer-event counts relative to the tracked wallet">Amount In / Out</th>
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
                title={`${row.inbound_transfer_count.toLocaleString("en-US")} inbound, ${row.outbound_transfer_count.toLocaleString("en-US")} outbound transfers`}
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
              title={event.is_indirect ? INDIRECT_TRANSFER_EXPLANATION : undefined}
            >
              {event.direction === "in" ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}
              {event.direction}{event.is_indirect ? "*" : ""}
            </span>
            <EtherscanLink
              className="addressLink"
              href={etherscanAddressUrl(event.counterparty_address)}
              title={`View ${event.counterparty_address} on Etherscan`}
            >
              <code>{shortAddress(event.counterparty_address)}</code>
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
  const [graphInteractionLimit, setGraphInteractionLimit] = useState(DEFAULT_GRAPH_INTERACTION_LIMIT);
  const [counterpartyLimit, setCounterpartyLimit] = useState(DEFAULT_COUNTERPARTY_LIMIT);
  const [graphTheaterMode, setGraphTheaterMode] = useState(false);
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

  const dashboardQuery = useMemo((): DashboardQuery => ({
    recognition: recognitionFilter,
    accountFilters: selectedAccountFilters,
    query: debouncedQuery,
    graphLimit: graphInteractionLimit,
    counterpartyLimit,
  }), [recognitionFilter, selectedAccountFilters, debouncedQuery, graphInteractionLimit, counterpartyLimit]);
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

  useEffect(() => setEventLimit(EVENT_PAGE_SIZE), [debouncedQuery, recognitionFilter, selectedAccountFilters]);
  useEffect(() => setCounterpartyLimit(DEFAULT_COUNTERPARTY_LIMIT), [debouncedQuery, recognitionFilter, selectedAccountFilters]);

  useEffect(() => () => {
    if (undoTimerRef.current != null) {
      window.clearTimeout(undoTimerRef.current);
    }
  }, []);

  useEffect(() => {
    if (!graphTheaterMode) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setGraphTheaterMode(false);
      }
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [graphTheaterMode]);

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
    const visibleCounterpartyNodeIds = new Set(
      data.graph.nodes
        .filter((node) => node.data.type === "counterparty" && node.data.accountType && accountVisible(node.data.accountType))
        .map((node) => node.data.id),
    );
    const visibleGraphEdges = data.graph.edges.filter((edge) =>
      edge.data.recognitionStatus != null && recognitionVisible(edge.data.recognitionStatus) &&
      visibleCounterpartyNodeIds.has(`counterparty:${edge.data.counterpartyAddress}`));
    const visibleNodeIds = new Set(visibleGraphEdges.flatMap((edge) => [edge.data.source, edge.data.target]));
    const visibleGraphNodes = data.graph.nodes.filter((node) => visibleNodeIds.has(node.data.id));
    const visibleTimeline = data.timeline.filter((row) =>
      recognitionVisible(row.recognition_status) &&
      accountVisible(row.counterparty_account_type));
    const visibleData = {
      ...data,
      events: visibleEvents,
      graph: { nodes: visibleGraphNodes, edges: visibleGraphEdges },
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
        event.ens,
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

    const interactionIds = new Set(
      events.map(
        (event) =>
          `interaction:${event.wallet_address}:${event.counterparty_address}:${event.token_address}:${event.direction}`,
      ),
    );
    const tokenAddresses = new Set([
      ...events.map((event) => event.token_address),
      ...directlyMatchedTokens.map((row) => row.token_address),
    ]);
    const counterpartyAddresses = new Set([
      ...events.map((event) => event.counterparty_address),
      ...directlyMatchedCounterparties.map((row) => row.counterparty_address),
    ]);
    const walletMatches = [data.metadata.ens, data.metadata.wallet_address]
      .some((value) => value.toLowerCase().includes(normalizedQuery));

    const tokens = visibleData.summaries.tokens.filter(
      (row) => tokenAddresses.has(row.token_address) || tokenMatches(row),
    );
    const counterparties = visibleData.summaries.counterparties.filter(
      (row) => counterpartyAddresses.has(row.counterparty_address),
    );

    const graphEdges = visibleData.graph.edges.filter((edge) =>
      walletMatches ||
      interactionIds.has(edge.data.interactionId) ||
      (edge.data.tokenAddress != null && tokenAddresses.has(edge.data.tokenAddress)) ||
      counterpartyAddresses.has(edge.data.counterpartyAddress) ||
      [edge.data.id, edge.data.direction, edge.data.tokenSymbol, edge.data.recognitionStatus,
        edge.data.recognitionSource, edge.data.metadataAvailability,
        edge.data.metadataSource, edge.data.target, edge.data.source]
        .some((value) => String(value).toLowerCase().includes(normalizedQuery)),
    );
    const connectedNodeIds = new Set(graphEdges.flatMap((edge) => [edge.data.source, edge.data.target]));
    const graphNodes = visibleData.graph.nodes.filter(
      (node) => connectedNodeIds.has(node.data.id) || node.data.label.toLowerCase().includes(normalizedQuery),
    );

    return {
      ...visibleData,
      events,
      graph: { nodes: graphNodes, edges: graphEdges },
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
    const counterpartyCount = new Set(filtered.events.map((event) => event.counterparty_address)).size;
    return { transferCount, tokenCount, counterpartyCount };
  }, [apiResult, data, filtered]);

  const displayedGraph = useMemo(() => {
    if (!filtered) {
      return null;
    }
    return buildCounterpartyGraph(filtered, graphInteractionLimit);
  }, [filtered, graphInteractionLimit]);

  const eventCount = dashboardDataMode === "api"
    ? (apiResult?.eventCount ?? 0)
    : (filtered?.events.length ?? 0);
  const tokenCount = dashboardDataMode === "api"
    ? (apiResult?.tokenCount ?? 0)
    : (filtered?.summaries.tokens.length ?? 0);
  const apiResultIsCurrent = dashboardDataMode !== "api" || apiResultQueryKey === dashboardQueryKey;

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

  function trapTheaterFocus(event: ReactKeyboardEvent<HTMLDivElement>) {
    if (!graphTheaterMode || event.key !== "Tab") {
      return;
    }

    const focusable = [...event.currentTarget.querySelectorAll<HTMLElement>(
      "button:not([disabled]), select:not([disabled]), a[href], [tabindex]:not([tabindex='-1'])",
    )];
    if (focusable.length === 0) {
      event.preventDefault();
      return;
    }

    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
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

  if (!data || !stats || !filtered || !displayedGraph) {
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
        <div>
          <h1>EVM Wallet Search</h1>
          <p>ERC20 token flow analytics for {data.metadata.ens}</p>
          <div className="snapshotSummary">
            <span>Data snapshot</span>
            <strong>{snapshotCoverageLabel(data.metadata)}</strong>
          </div>
          <div className={`provenance ${data.metadata.data_source}`} title={`Generated ${new Date(data.metadata.generated_at).toLocaleString()}`}>
            <span>{data.metadata.data_source === "fixture" ? "Fixture data" : "HyperIndex data"}</span>
            <span>{data.metadata.transfer_count.toLocaleString()} indexed transfers</span>
            <span title={accountEvidenceCoverageDescription(data.metadata)}>
              {accountEvidenceCoverageLabel(data.metadata)} · {accountEvidenceObservationBlockLabel(data.metadata.account_evidence_observation_block_number_min, data.metadata.account_evidence_observation_block_number_max)}
            </span>
            {data.metadata.is_sampled && (
              <span>{data.metadata.exported_event_count.toLocaleString()} recent events shown</span>
            )}
          </div>
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
            <details className="statusFilter accountFilter">
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

      <section className="stats" aria-label="Wallet summary">
        <Stat icon={Activity} label="Transfers" value={stats.transferCount.toString()} />
        <Stat icon={Database} label="Tokens" value={stats.tokenCount.toString()} />
        <Stat icon={Network} label="Counterparties" value={stats.counterpartyCount.toString()} />
      </section>

      <section className="workspace">
        {graphTheaterMode && (
          <div className="theaterBackdrop" aria-hidden="true" onClick={() => setGraphTheaterMode(false)} />
        )}
        <div
          className={`panel graphPanel${graphTheaterMode ? " theater" : ""}`}
          role={graphTheaterMode ? "dialog" : undefined}
          aria-modal={graphTheaterMode ? "true" : undefined}
          aria-label={graphTheaterMode ? "Counterparty Graph theater mode" : undefined}
          onKeyDown={trapTheaterFocus}
        >
          <div className="panelHeader">
            <div className="panelTitle">
              <h2>Counterparty Graph</h2>
              <p>One edge per address, ranked by captured transfers with the tracked wallet.</p>
            </div>
            <div className="graphHeaderControls">
              <span>{displayedGraph.nodes.length} nodes / {displayedGraph.edges.length} edges</span>
              {dashboardDataMode === "api" && apiResult && (
                <span>{displayedGraph.edges.length} of {apiResult.graphCounterpartyCount.toLocaleString("en-US")} counterparties</span>
              )}
              <label className="graphLimit">
                <span>Counterparties</span>
                <select
                  aria-label="Maximum graph counterparties"
                  value={graphInteractionLimit}
                  onChange={(event) => setGraphInteractionLimit(Number(event.target.value))}
                >
                  {GRAPH_INTERACTION_LIMITS.map((limit) => (
                    <option key={limit} value={limit}>{limit}</option>
                  ))}
                </select>
              </label>
              <button
                className="iconButton theaterToggle"
                type="button"
                onClick={() => setGraphTheaterMode((current) => !current)}
                aria-label={graphTheaterMode ? "Exit graph theater mode" : "Open graph theater mode"}
                title={graphTheaterMode ? "Exit theater mode (Esc)" : "Open graph theater mode"}
              >
                {graphTheaterMode ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
              </button>
            </div>
          </div>
          <Graph data={displayedGraph} theme={theme} theaterMode={graphTheaterMode} />
        </div>

        <div className="panel counterpartyPanel">
          <div className="panelHeader">
            <div className="panelTitle">
              <h2>Top ERC-20 Counterparties</h2>
              <p>Direct transfers; mint/burn, self, and token contracts excluded.</p>
            </div>
            <label className="graphLimit">
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

      <section className="panel lowerPanel">
        <div className="panelHeader">
          <div className="panelTitle">
            <h2>Token Flow</h2>
            <p>One row per token across inbound and outbound transfers.</p>
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
