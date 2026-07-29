import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  type AccountFilter,
  type AccountType,
  type ApiDashboardData,
  type DashboardData,
  type DashboardMetadata,
  type DashboardQuery,
  type RecognitionFilter,
  type RecognitionStatus,
  type TimelineBucket,
  type TimelineInterval,
  type WalletEvent,
  dashboardDataMode,
  loadApiDashboardData,
  loadDashboardData,
  loadNextApiEvents,
  resetTokenRecognition,
  setTokenRecognition,
} from "../data";
import {
  ACCOUNT_FILTERS,
  DEFAULT_COUNTERPARTY_LIMIT,
  EVENT_PAGE_SIZE,
  accountMatches,
  aggregateCounterparties,
  aggregateTimelineRows,
  aggregateTokenSummaries,
  bucketTimelineRows,
  timelineYears,
  utcDate,
  type DisplayedTokenSummary,
} from "./model";

type Theme = "light" | "dark";

export function useDashboard() {
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
      accountVisible(row.counterparty_account_type ?? "unknown"));
    const visibleCounterparties = data.summaries.counterparties.filter((row) =>
      recognitionVisible(row.recognition_status ?? "other") &&
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
        event.transaction_hash,
        event.wallet_address,
        event.counterparty_address,
        event.token_address,
        event.token_symbol,
        event.token_name,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));

    const tokenMatches = (row: DisplayedTokenSummary) =>
      [row.token_symbol, row.token_name, row.token_address]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery));

    const events = visibleData.events.filter(eventMatches);
    const directlyMatchedTokens = visibleData.summaries.tokens.filter(tokenMatches);
    const directlyMatchedCounterparties = visibleData.summaries.counterparties.filter((row) =>
      row.counterparty_address.toLowerCase().includes(normalizedQuery),
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

  return {
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
  };
}
