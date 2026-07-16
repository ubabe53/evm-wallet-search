import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";
import cytoscape from "cytoscape";
import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Database,
  ExternalLink,
  Maximize2,
  Minimize2,
  Moon,
  Network,
  RotateCcw,
  Search,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { AddressType, CounterpartySummary, DashboardData, DashboardGraph, GraphEdge, loadDashboardData, TokenStatus, TokenSummary, WalletEvent } from "./data";

type Theme = "light" | "dark";
const EVENT_PAGE_SIZE = 10;
const DEFAULT_GRAPH_INTERACTION_LIMIT = 25;
const GRAPH_INTERACTION_LIMITS = [10, 25, 50, 100] as const;
const DEFAULT_COUNTERPARTY_LIMIT = 10;
const COUNTERPARTY_LIMITS = [10, 25, 50] as const;
const TOKEN_STATUSES: TokenStatus[] = ["trusted", "unverified", "suspected_spam", "spam"];
const DEFAULT_TOKEN_STATUSES: TokenStatus[] = ["trusted", "unverified"];
const ZERO_ADDRESS = "0x0000000000000000000000000000000000000000";
const ETHERSCAN_BASE_URL = "https://etherscan.io";

export function etherscanAddressUrl(address: string): string {
  return `${ETHERSCAN_BASE_URL}/address/${address}`;
}

export function etherscanTokenUrl(address: string): string {
  return `${ETHERSCAN_BASE_URL}/token/${address}`;
}

export function etherscanTransactionUrl(hash: string): string {
  return `${ETHERSCAN_BASE_URL}/tx/${hash}`;
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

function shortAddress(address: string): string {
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

function compactAddress(address: string): string {
  return `${address.slice(0, 5)}...${address.slice(-3)}`;
}

function amountLabel(value: number | null | undefined): string {
  if (value == null) {
    return "amount unavailable";
  }
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 4 }).format(value);
}

type RankedCounterparty = Omit<CounterpartySummary, "token_status">;

export function aggregateCounterparties(rows: CounterpartySummary[]): RankedCounterparty[] {
  const grouped = new Map<string, RankedCounterparty>();

  for (const row of rows) {
    const existing = grouped.get(row.counterparty_address);
    if (!existing) {
      const { token_status: _tokenStatus, ...summary } = row;
      grouped.set(row.counterparty_address, { ...summary });
      continue;
    }

    existing.transfer_count += row.transfer_count;
    existing.inbound_transfer_count += row.inbound_transfer_count;
    existing.outbound_transfer_count += row.outbound_transfer_count;
    existing.token_count += row.token_count;
    existing.first_seen_at = existing.first_seen_at < row.first_seen_at ? existing.first_seen_at : row.first_seen_at;
    existing.last_seen_at = existing.last_seen_at > row.last_seen_at ? existing.last_seen_at : row.last_seen_at;
    if (existing.counterparty_type === "unknown" && row.counterparty_type !== "unknown") {
      existing.counterparty_type = row.counterparty_type;
    }
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

export function interactionEdgeLabel(tokenSymbol: string, transferCount: number): string {
  return `${tokenSymbol} x${transferCount.toLocaleString("en-US")}`;
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

function TokenStatusBadge({
  status,
  source,
  reputationScore,
  reputationReasons,
  interactionScore,
  interactionReasons,
}: {
  status: TokenSummary["token_status"];
  source: string | null;
  reputationScore?: number;
  reputationReasons?: string;
  interactionScore?: number;
  interactionReasons?: string;
}) {
  const title = status === "trusted" && source
    ? `Trusted metadata from ${source.replace("+", " and ")}`
    : status === "spam"
      ? "Explicitly reviewed as spam"
      : status === "suspected_spam"
        ? [
          `Automated suspected-spam classification`,
          reputationScore != null ? `token score ${reputationScore}: ${reputationReasons}` : null,
          interactionScore != null ? `interaction score ${interactionScore}: ${interactionReasons}` : null,
        ].filter(Boolean).join("; ")
        : "Not present in the curated token registry";
  return <span className={`tokenStatus ${status}`} title={title}>{status.replace("_", " ")}</span>;
}

function AddressTypeBadge({ type }: { type: AddressType }) {
  const title = type === "contract"
    ? "Contract bytecode exists at the pinned Ethereum block"
    : type === "wallet"
      ? "No contract bytecode at the pinned Ethereum block"
      : "Address has not been classified or the bytecode check failed";
  return <span className={`addressType ${type}`} title={title}>{type}</span>;
}

function graphStyles(container: HTMLElement): cytoscape.StylesheetJson {
  const styles = getComputedStyle(container);
  const nodeText = styles.getPropertyValue("--graph-label").trim();
  const edgeColor = styles.getPropertyValue("--graph-edge").trim();
  const counterpartyColor = styles.getPropertyValue("--graph-counterparty").trim();
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
      selector: 'node[addressType = "contract"]',
      style: { shape: "round-rectangle" },
    },
    {
      selector: 'node[addressType = "unknown"]',
      style: { "border-style": "dashed" },
    },
    {
      selector: "edge",
      style: {
        width: "mapData(transferCount, 1, 100, 0.65, 2.2)",
        "line-color": edgeColor,
        "target-arrow-color": edgeColor,
        "target-arrow-shape": "triangle",
        "arrow-scale": 0.65,
        opacity: 0.58,
        "curve-style": "bezier",
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
      layout: { name: "cose", animate: false, fit: true, padding: 30 },
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
      const tokenAddress = event.target.data("tokenAddress");
      if (tokenAddress) {
        openEtherscan(etherscanTokenUrl(tokenAddress));
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
        aria-label={`Wallet interaction graph with ${data.nodes.length} nodes and ${data.edges.length} edges`}
      />
      {data.nodes.length === 0 && <div className="graphEmpty">No graph matches</div>}
      <div className="graphLegend" aria-label="Graph legend">
        <span><i className="walletSwatch" />Tracked wallet</span>
        <span><i className="contractSwatch" />Contract</span>
        <span><i className="counterpartySwatch" />Wallet</span>
        <span><i className="unknownSwatch" />Unknown</span>
      </div>
    </div>
  );
}

function TokenTable({ rows }: { rows: TokenSummary[] }) {
  return (
    <table>
      <thead>
        <tr>
          <th>Token</th>
          <th>Status</th>
          <th>Transfers</th>
          <th>Senders | Recipients</th>
          <th>Counterparties</th>
        </tr>
      </thead>
      <tbody>
        {rows.length === 0 && (
          <tr>
            <td className="tableEmpty" colSpan={5}>No token flows match</td>
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
            <td><TokenStatusBadge
              status={row.token_status}
              source={row.metadata_source}
              reputationScore={row.token_reputation_score}
              reputationReasons={row.token_reputation_reasons}
            /></td>
            <td>{row.transfer_count.toLocaleString("en-US")}</td>
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
                <AddressTypeBadge type={row.counterparty_type} />
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
  onShowMore,
  onShowLess,
}: {
  events: WalletEvent[];
  limit: number;
  onShowMore: () => void;
  onShowLess: () => void;
}) {
  const visibleEvents = events.slice(0, limit);
  const canShowLess = limit > EVENT_PAGE_SIZE && events.length > EVENT_PAGE_SIZE;
  const canShowMore = visibleEvents.length < events.length;

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
            <TokenStatusBadge
              status={event.token_status}
              source={event.metadata_source}
              reputationScore={event.token_reputation_score}
              reputationReasons={event.token_reputation_reasons}
              interactionScore={event.interaction_legitimacy_score}
              interactionReasons={event.interaction_legitimacy_reasons}
            />
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
            <span className={`direction ${event.direction}`}>
              {event.direction === "in" ? <ArrowDownLeft size={14} /> : <ArrowUpRight size={14} />}
              {event.direction}
            </span>
            <span>{amountLabel(event.amount_decimal)}</span>
            <EtherscanLink
              className="addressLink"
              href={etherscanAddressUrl(event.counterparty_address)}
              title={`View ${event.counterparty_address} on Etherscan`}
            >
              <code>{shortAddress(event.counterparty_address)}</code>
            </EtherscanLink>
            <AddressTypeBadge type={event.counterparty_type} />
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
            <button className="eventPageButton" type="button" onClick={onShowMore}>
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
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [eventLimit, setEventLimit] = useState(EVENT_PAGE_SIZE);
  const [graphInteractionLimit, setGraphInteractionLimit] = useState(DEFAULT_GRAPH_INTERACTION_LIMIT);
  const [counterpartyLimit, setCounterpartyLimit] = useState(DEFAULT_COUNTERPARTY_LIMIT);
  const [graphTheaterMode, setGraphTheaterMode] = useState(false);
  const [selectedStatuses, setSelectedStatuses] = useState<TokenStatus[]>(DEFAULT_TOKEN_STATUSES);
  const [theme, setTheme] = useState<Theme>(() => {
    const saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      return saved;
    }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });

  useEffect(() => {
    const controller = new AbortController();
    loadDashboardData(controller.signal).then(setData).catch((loadError: unknown) => {
      if (loadError instanceof Error && loadError.name === "AbortError") {
        return;
      }
      setError(loadError instanceof Error ? loadError.message : "Could not load dashboard data");
    });
    return () => controller.abort();
  }, []);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("theme", theme);
  }, [theme]);

  useEffect(() => setEventLimit(EVENT_PAGE_SIZE), [data, query, selectedStatuses]);
  useEffect(() => setCounterpartyLimit(DEFAULT_COUNTERPARTY_LIMIT), [data, query, selectedStatuses]);

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

    const statusVisible = (status: TokenSummary["token_status"]) =>
      selectedStatuses.includes(status);
    const visibleEvents = data.events.filter((event) => statusVisible(event.token_status));
    const visibleTokens = data.summaries.tokens.filter((row) => statusVisible(row.token_status));
    const visibleCounterparties = data.summaries.counterparties.filter((row) => statusVisible(row.token_status));
    const visibleGraphEdges = data.graph.edges.filter((edge) => statusVisible(edge.data.tokenStatus));
    const visibleNodeIds = new Set(visibleGraphEdges.flatMap((edge) => [edge.data.source, edge.data.target]));
    const visibleGraphNodes = data.graph.nodes.filter((node) => visibleNodeIds.has(node.data.id));
    const visibleTimeline = data.timeline.filter((row) => statusVisible(row.token_status));
    const visibleData = {
      ...data,
      events: visibleEvents,
      graph: { nodes: visibleGraphNodes, edges: visibleGraphEdges },
      summaries: { tokens: visibleTokens, counterparties: visibleCounterparties },
      timeline: visibleTimeline,
    };

    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) {
      return visibleData;
    }

    const eventMatches = (event: WalletEvent) =>
      [
        event.transfer_id,
        event.transaction_hash,
        event.block_date,
        event.direction,
        event.ens,
        event.wallet_address,
        event.counterparty_address,
        event.counterparty_type,
        event.token_address,
        event.token_symbol,
        event.token_name,
        event.token_status,
        event.token_reputation,
        event.token_reputation_reasons,
        event.interaction_legitimacy,
        event.interaction_legitimacy_reasons,
        event.metadata_source,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));

    const tokenMatches = (row: TokenSummary) =>
      [row.token_symbol, row.token_name, row.token_address, row.token_status, row.metadata_source,
        row.token_reputation, row.token_reputation_reasons]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));

    const events = visibleData.events.filter(eventMatches);
    const directlyMatchedTokens = visibleData.summaries.tokens.filter(tokenMatches);
    const directlyMatchedCounterparties = visibleData.summaries.counterparties.filter((row) =>
      [row.counterparty_address, row.counterparty_type, row.token_status]
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
      tokenAddresses.has(edge.data.tokenAddress) ||
      counterpartyAddresses.has(edge.data.counterpartyAddress) ||
      [edge.data.id, edge.data.direction, edge.data.tokenSymbol, edge.data.tokenStatus,
        edge.data.metadataSource, edge.data.tokenReputation, edge.data.tokenReputationReasons,
        edge.data.interactionLegitimacy, edge.data.interactionLegitimacyReasons, edge.data.target, edge.data.source]
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
  }, [data, query, selectedStatuses]);

  const rankedCounterparties = useMemo(
    () => filtered ? aggregateCounterparties(filtered.summaries.counterparties) : [],
    [filtered],
  );

  const stats = useMemo(() => {
    if (!filtered || !data) {
      return null;
    }
    if (!query.trim()) {
      const statusKey = TOKEN_STATUSES.filter((status) => selectedStatuses.includes(status)).join("+");
      const statusMetrics = data.metadata.status_counts[statusKey] ?? {
        transfer_count: 0,
        token_count: 0,
        counterparty_count: 0,
      };
      return {
        transferCount: statusMetrics.transfer_count,
        tokenCount: statusMetrics.token_count,
        counterpartyCount: statusMetrics.counterparty_count,
      };
    }
    const transferCount = filtered.events.length;
    const tokenCount = new Set(filtered.events.map((event) => event.token_address)).size;
    const counterpartyCount = new Set(filtered.events.map((event) => event.counterparty_address)).size;
    return { transferCount, tokenCount, counterpartyCount };
  }, [data, filtered, query, selectedStatuses]);

  const displayedGraph = useMemo(() => {
    if (!filtered) {
      return null;
    }

    const interactionIds = new Set<string>();
    for (const edge of filtered.graph.edges) {
      if (edge.data.counterpartyAddress === ZERO_ADDRESS) {
        continue;
      }
      if (interactionIds.has(edge.data.interactionId)) {
        continue;
      }
      if (interactionIds.size === graphInteractionLimit) {
        break;
      }
      interactionIds.add(edge.data.interactionId);
    }

    const representativeEdges = new Map<string, GraphEdge>();
    for (const edge of filtered.graph.edges) {
      if (interactionIds.has(edge.data.interactionId) && !representativeEdges.has(edge.data.interactionId)) {
        representativeEdges.set(edge.data.interactionId, edge);
      }
    }

    const edges = [...representativeEdges.values()].map((edge): GraphEdge => {
      const walletNodeId = `wallet:${edge.data.walletAddress}`;
      const counterpartyNodeId = `counterparty:${edge.data.counterpartyAddress}`;
      return {
        data: {
          ...edge.data,
          id: `${edge.data.interactionId}:wallet-counterparty`,
          label: interactionEdgeLabel(edge.data.tokenSymbol, edge.data.transferCount),
          edgeRole: "wallet_counterparty",
          source: edge.data.direction === "out" ? walletNodeId : counterpartyNodeId,
          target: edge.data.direction === "out" ? counterpartyNodeId : walletNodeId,
        },
      };
    });
    const nodeIds = new Set(edges.flatMap((edge) => [edge.data.source, edge.data.target]));
    const counterpartyCounts = new Map<string, number>();
    for (const edge of edges) {
      counterpartyCounts.set(
        `counterparty:${edge.data.counterpartyAddress}`,
        edge.data.counterpartyTransferCount,
      );
    }
    const nodes = filtered.graph.nodes
      .filter((node) => node.data.type !== "token" && nodeIds.has(node.data.id))
      .map((node) => {
        if (node.data.type === "wallet") {
          return { data: { ...node.data, size: 44 } };
        }
        const transferCount = counterpartyCounts.get(node.data.id) ?? 1;
        return {
          data: {
            ...node.data,
            size: counterpartyNodeSize(transferCount),
            transferCount,
          },
        };
      });
    return { nodes, edges };
  }, [filtered, graphInteractionLimit]);

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
          <p>{error}. Run `bun run analytics:build` and `bun run export:dashboard`.</p>
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
          <div className={`provenance ${data.metadata.data_source}`} title={`Generated ${new Date(data.metadata.generated_at).toLocaleString()}`}>
            <span>{data.metadata.data_source === "fixture" ? "Fixture data" : "HyperIndex data"}</span>
            <span>{data.metadata.transfer_count.toLocaleString()} indexed transfers</span>
            {data.metadata.is_sampled && (
              <span>{data.metadata.exported_event_count.toLocaleString()} recent events shown</span>
            )}
          </div>
        </div>
        <div className="toolbar">
          <details className="statusFilter">
            <summary>
              Status ({selectedStatuses.length})
              <ChevronDown size={14} aria-hidden="true" />
            </summary>
            <div className="statusMenu" role="group" aria-label="Token status filter">
              {TOKEN_STATUSES.map((status) => (
                <label key={status}>
                  <input
                    type="checkbox"
                    checked={selectedStatuses.includes(status)}
                    onChange={(event) => setSelectedStatuses((current) => event.target.checked
                      ? [...current.filter((value) => value !== status), status]
                      : current.filter((value) => value !== status))}
                  />
                  <TokenStatusBadge status={status} source={null} />
                </label>
              ))}
            </div>
          </details>
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
          aria-label={graphTheaterMode ? "Interaction Graph theater mode" : undefined}
          onKeyDown={trapTheaterFocus}
        >
          <div className="panelHeader">
            <h2>Interaction Graph</h2>
            <div className="graphHeaderControls">
              <span>{displayedGraph.nodes.length} nodes / {displayedGraph.edges.length} edges</span>
              <label className="graphLimit">
                <span>Interactions</span>
                <select
                  aria-label="Maximum graph interactions"
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
        </div>
      </section>

      <section className="panel">
          <div className="panelHeader">
            <h2>Recent Events</h2>
            <span>
              {Math.min(eventLimit, filtered.events.length)} of {filtered.events.length} events
            </span>
          </div>
        <EventList
          events={filtered.events}
          limit={eventLimit}
          onShowMore={() => setEventLimit((current) => current + EVENT_PAGE_SIZE)}
          onShowLess={() => setEventLimit((current) => Math.max(EVENT_PAGE_SIZE, current - EVENT_PAGE_SIZE))}
        />
      </section>

      <section className="panel lowerPanel">
        <div className="panelHeader">
          <div className="panelTitle">
            <h2>Token Flow</h2>
            <p>One row per token across inbound and outbound transfers.</p>
          </div>
          <span>{filtered.summaries.tokens.length} tokens</span>
        </div>
        <div className="tokenTableScroll compact">
          <TokenTable rows={filtered.summaries.tokens} />
        </div>
      </section>
    </main>
  );
}
