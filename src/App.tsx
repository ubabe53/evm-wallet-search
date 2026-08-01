import {
  Activity,
  ChevronDown,
  Database,
  ExternalLink,
  Moon,
  Network,
  Search,
  Sun,
} from "lucide-react";
import { useRef, useState } from "react";
import { dashboardDataMode } from "./data";
import { ActivityTimeline } from "./dashboard/ActivityTimeline";
import { CounterpartyTable } from "./dashboard/CounterpartyTable";
import { EventList } from "./dashboard/EventList";
import { TokenTable } from "./dashboard/TokenTable";
import { EtherscanLink, InfoTooltip, Stat } from "./dashboard/components";
import {
  ACCOUNT_FILTERS,
  ACCOUNT_LABELS,
  COUNTERPARTY_LIMITS,
  EVENT_PAGE_SIZE,
  RECOGNITION_FILTERS,
  accountEvidenceCoverageDescription,
  accountEvidenceCoverageLabel,
  accountEvidenceObservationBlockLabel,
  compactAddress,
  etherscanAddressUrl,
  generatedAtLabel,
  snapshotCoverageLabel,
} from "./dashboard/model";
import { useDashboard } from "./dashboard/useDashboard";

export function App() {
  const [scanOpen, setScanOpen] = useState(false);
  const touchActivation = useRef(false);
  const {
    apiResult,
    apiResultIsCurrent,
    availableTimelineYears,
    changeTimelineYear,
    changeTokenRecognition,
    counterpartyLimit,
    data,
    error,
    eventCount,
    eventLimit,
    filtered,
    loadingMoreEvents,
    recognitionActionError,
    recognitionFilter,
    rankedCounterparties,
    selectTimelineBucket,
    selectedAccountFilters,
    selectedMonth,
    selectedYear,
    setCounterpartyLimit,
    setEventLimit,
    setQuery,
    setRecognitionFilter,
    setSelectedAccountFilters,
    setSelectedMonth,
    setTheme,
    showMoreEvents,
    stats,
    theme,
    timelineBuckets,
    timelineInterval,
    tokenCount,
    undoAction,
    undoTokenRecognition,
    updatingToken,
    query,
    scanError,
    scanInput,
    scanJob,
    setScanInput,
    startWalletScan,
    wallets,
  } = useDashboard();
  const scanBusy = scanJob?.status === "queued" || scanJob?.status === "running";

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
          <div
            className="scanLauncher"
            onMouseEnter={() => {
              if (!touchActivation.current) setScanOpen(true);
            }}
            onMouseLeave={() => setScanOpen(false)}
            onFocus={() => {
              if (!touchActivation.current) setScanOpen(true);
            }}
            onBlur={(event) => {
              const next = event.relatedTarget as Node | null;
              if (!next || !event.currentTarget.contains(next)) setScanOpen(false);
            }}
          >
            <button
              className="scanLauncherButton"
              type="button"
              onPointerDown={(event) => {
                if (event.pointerType === "touch" || event.pointerType === "pen") {
                  touchActivation.current = true;
                }
              }}
              onClick={(event) => {
                if (touchActivation.current) {
                  touchActivation.current = false;
                  setScanOpen((open) => !open);
                } else {
                  setScanOpen(true);
                }
              }}
              aria-expanded={scanOpen}
              aria-controls="wallet-scan-panel"
            >
              <span>Scan wallet</span>
              <ChevronDown size={14} aria-hidden="true" />
            </button>
            {scanOpen && (
              <div className="scanLauncherPanel" id="wallet-scan-panel" aria-label="Wallet scan">
                <div className="scanHeader">
                  <div>
                    <strong>Change analysis wallet</strong>
                    <p>Scan from block 0 through the finalized head.</p>
                  </div>
                  <span className={`scanHint ${dashboardDataMode === "api" ? "live" : "fixture"}`}>
                    {dashboardDataMode === "api" ? "Live mode" : "Fixture demo"}
                  </span>
                </div>
                <form className="scanForm" onSubmit={(event) => { event.preventDefault(); void startWalletScan(); }}>
                  <label>
                    <span className="srOnly">Wallet address or ENS</span>
                    <input
                      className="scanInput"
                      value={scanInput}
                      onChange={(event) => setScanInput(event.target.value)}
                      placeholder="0x… or name.eth"
                      aria-label="Wallet address or ENS"
                      disabled={dashboardDataMode === "static" || scanBusy}
                    />
                  </label>
                  <button className="scanButton" type="submit" disabled={dashboardDataMode === "static" || !scanInput.trim() || scanBusy}>
                    {scanBusy ? "Scanning…" : "Start scan"}
                  </button>
                </form>
                {scanBusy && (
                  <div className="scanProgress" role="status" aria-live="polite">
                    <span>Scanning {scanJob.wallet_label} · {scanJob.progress}%</span>
                    <progress max="100" value={scanJob.progress}>{scanJob.progress}%</progress>
                  </div>
                )}
                {scanJob?.status === "completed" && <p className="scanSuccess" role="status">Scan complete. Switched to {scanJob.wallet_label}.</p>}
                {(scanError || scanJob?.status === "failed") && <p className="scanError" role="alert">{scanError ?? scanJob?.error}</p>}
                {wallets.length > 0 && (
                  <div className="walletList" aria-label="Completed wallets">
                    <span>Completed wallets:</span>
                    {wallets.map((wallet) => <span key={wallet.wallet_address} className={wallet.wallet_address === data.metadata.wallet_address ? "currentWallet" : ""}>{wallet.label}</span>)}
                  </div>
                )}
                {dashboardDataMode === "static" && <p className="boundedNote">Wallet scanning is available only in live local mode.</p>}
              </div>
            )}
          </div>
          <div className="filterBar" aria-label="Dashboard filters">
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
          </div>
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
              {data.metadata.configured_wallet_label}
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
