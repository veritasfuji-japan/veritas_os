"use client";

import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { veritasFetch } from "../../../lib/api-client";
import {
  isRequestLogResponse,
  isTrustLogsResponse,
  type RequestLogResponse,
  type TrustLogItem,
} from "../../../lib/api-validators";
import { useI18n } from "../../../components/i18n-provider";
import {
  classifyChain,
  computeAuditSummary,
  type AuditSummary,
  type ChainResult,
  type CrossSearchParams,
  type DetailTab,
  type ExportFormat,
  type RedactionMode,
} from "../audit-types";
import { PAGE_LIMIT } from "../constants";

/* ------------------------------------------------------------------ */
/*  Return type                                                        */
/* ------------------------------------------------------------------ */

export interface AuditDataState {
  /* data */
  items: TrustLogItem[];
  cursor: string | null;
  hasMore: boolean;
  loading: boolean;
  error: string | null;

  /* selected */
  selected: TrustLogItem | null;
  setSelected: (item: TrustLogItem | null) => void;

  /* search */
  requestId: string;
  setRequestId: (v: string) => void;
  requestResult: RequestLogResponse | null;
  stageFilter: string;
  setStageFilter: (v: string) => void;
  crossSearch: CrossSearchParams;
  setCrossSearch: Dispatch<SetStateAction<CrossSearchParams>>;
  selectedDecisionId: string;
  setSelectedDecisionId: (v: string) => void;
  verificationMessage: string;
  setVerificationMessage: (v: string) => void;

  /* detail tab */
  detailTab: DetailTab;
  setDetailTab: (v: DetailTab) => void;

  /* export */
  reportStartDate: string;
  setReportStartDate: (v: string) => void;
  reportEndDate: string;
  setReportEndDate: (v: string) => void;
  reportError: string | null;
  setReportError: (v: string | null) => void;
  latestReport: import("../audit-types").RegulatoryReport | null;
  setLatestReport: (v: import("../audit-types").RegulatoryReport | null) => void;
  confirmPiiRisk: boolean;
  setConfirmPiiRisk: (v: boolean) => void;
  redactionMode: RedactionMode;
  setRedactionMode: (v: RedactionMode) => void;
  exportFormat: ExportFormat;
  setExportFormat: (v: ExportFormat) => void;

  /* derived */
  sortedItems: TrustLogItem[];
  stageOptions: string[];
  filteredItems: TrustLogItem[];
  auditSummary: AuditSummary;
  decisionIds: string[];
  selectedDecisionEntry: TrustLogItem | null;
  selectedIndex: number;
  previousEntry: TrustLogItem | null;
  nextEntry: TrustLogItem | null;
  selectedChain: ChainResult | null;
  exportTargetCount: number;

  /* actions */
  loadLogs: (nextCursor: string | null, replace: boolean) => Promise<void>;
  searchByRequestId: () => Promise<void>;
}

/* ------------------------------------------------------------------ */
/*  Hook                                                               */
/* ------------------------------------------------------------------ */

export function useAuditData(): AuditDataState {
  const { t } = useI18n();

  /* -- data state -------------------------------------------------- */
  const [cursor, setCursor] = useState<string | null>(null);
  const [items, setItems] = useState<TrustLogItem[]>([]);
  const [selected, setSelected] = useState<TrustLogItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);

  /* -- search state ------------------------------------------------ */
  const [requestId, setRequestId] = useState("");
  const [requestResult, setRequestResult] = useState<RequestLogResponse | null>(null);
  const [stageFilter, setStageFilter] = useState("ALL");
  const [crossSearch, setCrossSearch] = useState<CrossSearchParams>({ query: "", field: "all" });
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const [verificationMessage, setVerificationMessage] = useState("");

  /* -- detail tab state -------------------------------------------- */
  const [detailTab, setDetailTab] = useState<DetailTab>("summary");

  /* -- export state ------------------------------------------------ */
  const [reportStartDate, setReportStartDate] = useState("");
  const [reportEndDate, setReportEndDate] = useState("");
  const [reportError, setReportError] = useState<string | null>(null);
  const [latestReport, setLatestReport] = useState<import("../audit-types").RegulatoryReport | null>(null);
  const [confirmPiiRisk, setConfirmPiiRisk] = useState(false);
  const [redactionMode, setRedactionMode] = useState<RedactionMode>("full");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("json");

  const requestSearchNonceRef = useRef(0);
  const loadAbortRef = useRef<AbortController | null>(null);

  /* ---------------------------------------------------------------- */
  /*  Derived data                                                     */
  /* ---------------------------------------------------------------- */

  const sortedItems = useMemo(
    () =>
      [...items].sort(
        (a, b) =>
          new Date(b.created_at ?? "").getTime() -
          new Date(a.created_at ?? "").getTime(),
      ),
    [items],
  );

  const stageOptions = useMemo(() => {
    const stages = new Set<string>();
    for (const item of sortedItems) {
      stages.add(typeof item.stage === "string" ? item.stage : "UNKNOWN");
    }
    return ["ALL", ...Array.from(stages).sort()];
  }, [sortedItems]);

  const filteredItems = useMemo(() => {
    const query = crossSearch.query.trim().toLowerCase();
    return sortedItems.filter((item) => {
      if (stageFilter !== "ALL" && item.stage !== stageFilter) return false;
      if (!query) return true;

      const field = crossSearch.field;
      if (field === "decision_id") return String(item.decision_id ?? "").toLowerCase().includes(query);
      if (field === "request_id") return String(item.request_id ?? "").toLowerCase().includes(query);
      if (field === "replay_id") return String(item.replay_id ?? "").toLowerCase().includes(query);
      if (field === "policy_version") return String(item.policy_version ?? "").toLowerCase().includes(query);

      // "all" — search across all relevant fields
      const haystack = [
        item.request_id,
        item.decision_id,
        item.replay_id,
        item.policy_version,
      ]
        .map((v) => String(v ?? "").toLowerCase())
        .join(" ");
      return haystack.includes(query);
    });
  }, [crossSearch, sortedItems, stageFilter]);

  const auditSummary: AuditSummary = useMemo(
    () => computeAuditSummary(filteredItems),
    [filteredItems],
  );

  const decisionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of sortedItems) {
      const decisionId = item.decision_id;
      const fallback = item.request_id;
      if (typeof decisionId === "string" && decisionId.length > 0) ids.add(decisionId);
      else if (typeof fallback === "string" && fallback.length > 0) ids.add(fallback);
    }
    return Array.from(ids).sort();
  }, [sortedItems]);

  const selectedDecisionEntry = useMemo(() => {
    if (!selectedDecisionId) return null;
    return (
      sortedItems.find(
        (item) =>
          item.decision_id === selectedDecisionId ||
          item.request_id === selectedDecisionId,
      ) ?? null
    );
  }, [selectedDecisionId, sortedItems]);

  const selectedIndex = useMemo(
    () => (selected ? filteredItems.findIndex((item) => item === selected) : -1),
    [filteredItems, selected],
  );
  const previousEntry =
    selectedIndex >= 0 ? filteredItems[selectedIndex + 1] ?? null : null;
  const nextEntry =
    selectedIndex > 0 ? filteredItems[selectedIndex - 1] ?? null : null;

  const selectedChain: ChainResult | null = useMemo(
    () => (selected ? classifyChain(selected, previousEntry) : null),
    [previousEntry, selected],
  );

  const exportTargetCount = useMemo(() => {
    if (!reportStartDate || !reportEndDate) return 0;
    const start = new Date(`${reportStartDate}T00:00:00.000Z`).getTime();
    const end = new Date(`${reportEndDate}T23:59:59.999Z`).getTime();
    return sortedItems.filter((item) => {
      const stamp = new Date(item.created_at ?? "").getTime();
      return Number.isFinite(stamp) && stamp >= start && stamp <= end;
    }).length;
  }, [reportStartDate, reportEndDate, sortedItems]);

  /* ---------------------------------------------------------------- */
  /*  Actions                                                          */
  /* ---------------------------------------------------------------- */

  const loadLogs = async (
    nextCursor: string | null,
    replace: boolean,
  ): Promise<void> => {
    // Cancel any in-flight loadLogs request before starting a new one
    loadAbortRef.current?.abort();
    const controller = new AbortController();
    loadAbortRef.current = controller;

    setError(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_LIMIT) });
      if (nextCursor) params.set("cursor", nextCursor);
      const response = await veritasFetch(
        `/api/veritas/v1/trust/logs?${params.toString()}`,
        { signal: controller.signal },
      );
      if (!response.ok) {
        setError(
          `HTTP ${response.status}: ${t("trust logs取得に失敗しました。", "Failed to fetch trust logs.")}`,
        );
        return;
      }
      const payload: unknown = await response.json();
      if (!isTrustLogsResponse(payload)) {
        setError(
          t(
            "レスポンス形式エラー: trust logs の形式が不正です。",
            "Response format error: trust logs payload is invalid.",
          ),
        );
        return;
      }
      const nextItems = payload.items;
      setItems((prev) => (replace ? nextItems : [...prev, ...nextItems]));
      setCursor(payload.next_cursor);
      setHasMore(Boolean(payload.has_more));
      if (replace && nextItems.length > 0) setSelected(nextItems[0]);
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        // Cancelled by a newer loadLogs call — silently drop the stale request
        if (loadAbortRef.current !== controller) return;
        setError(
          t(
            "タイムアウト: trust logs 取得が時間内に完了しませんでした。",
            "Timeout: trust logs request did not complete in time.",
          ),
        );
        return;
      }
      setError(
        t(
          "ネットワークエラー: trust logs 取得に失敗しました。",
          "Network error: failed to fetch trust logs.",
        ),
      );
    } finally {
      if (loadAbortRef.current === controller) {
        setLoading(false);
      }
    }
  };

  const searchByRequestId = async (): Promise<void> => {
    const value = requestId.trim();
    requestSearchNonceRef.current += 1;
    const requestNonce = requestSearchNonceRef.current;
    setRequestResult(null);
    setError(null);
    if (!value) {
      setError(t("request_id を入力してください。", "Please enter request_id."));
      return;
    }
    setLoading(true);
    try {
      const response = await veritasFetch(
        `/api/veritas/v1/trust/${encodeURIComponent(value)}`,
      );
      if (!response.ok) {
        setError(
          `HTTP ${response.status}: ${t("request_id 検索に失敗しました。", "Failed to search request_id.")}`,
        );
        return;
      }
      const payload: unknown = await response.json();
      if (requestNonce !== requestSearchNonceRef.current) return;
      if (!isRequestLogResponse(payload)) {
        setError(
          t(
            "レスポンス形式エラー: request_id 応答の形式が不正です。",
            "Response format error: request_id payload is invalid.",
          ),
        );
        return;
      }
      setRequestResult(payload);
      if (payload.items.length > 0)
        setSelected(payload.items[payload.items.length - 1]);
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError(
          t(
            "タイムアウト: request_id 検索が時間内に完了しませんでした。",
            "Timeout: request_id search did not complete in time.",
          ),
        );
        return;
      }
      setError(
        t(
          "ネットワークエラー: request_id 検索に失敗しました。",
          "Network error: failed to search request_id.",
        ),
      );
    } finally {
      if (requestNonce === requestSearchNonceRef.current) setLoading(false);
    }
  };

  useEffect(() => {
    if (!selected && filteredItems.length > 0) setSelected(filteredItems[0]);
  }, [filteredItems, selected]);

  /* ---------------------------------------------------------------- */
  /*  Return                                                           */
  /* ---------------------------------------------------------------- */

  return {
    items,
    cursor,
    hasMore,
    loading,
    error,
    selected,
    setSelected,
    requestId,
    setRequestId,
    requestResult,
    stageFilter,
    setStageFilter,
    crossSearch,
    setCrossSearch,
    selectedDecisionId,
    setSelectedDecisionId,
    verificationMessage,
    setVerificationMessage,
    detailTab,
    setDetailTab,
    reportStartDate,
    setReportStartDate,
    reportEndDate,
    setReportEndDate,
    reportError,
    setReportError,
    latestReport,
    setLatestReport,
    confirmPiiRisk,
    setConfirmPiiRisk,
    redactionMode,
    setRedactionMode,
    exportFormat,
    setExportFormat,
    sortedItems,
    stageOptions,
    filteredItems,
    auditSummary,
    decisionIds,
    selectedDecisionEntry,
    selectedIndex,
    previousEntry,
    nextEntry,
    selectedChain,
    exportTargetCount,
    loadLogs,
    searchByRequestId,
  };
}
