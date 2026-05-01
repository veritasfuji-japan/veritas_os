"use client";

import { type Dispatch, type SetStateAction, useEffect, useMemo, useRef, useState } from "react";
import { veritasFetch } from "../../../lib/api-client";
import {
  isRequestLogResponse,
  isTrustLogsResponse,
  type RequestLogResponse,
  type TrustLogItem,
} from "@veritas/types";
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
  bindReceiptLookupError: string | null;
  bindReceiptLookupLoading: boolean;
  bindReceiptIdFromQuery: string | null;
  bindReceiptFoundInTimeline: boolean;
  bindReceiptLookupDetail: BindReceiptLookupDetail | null;
  bindReceiptLookupSucceeded: boolean;
  bindReceiptTimelineMiss: boolean;
  showBindReceiptFallback: boolean;
  decisionIdFromQuery: string | null;
  executionIntentIdFromQuery: string | null;
  queryTraceStatus: string | null;

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

interface BindReceiptLookupDetail {
  bindReceiptId: string;
  executionIntentId: string | null;
  finalOutcome: string | null;
  bindFailureReason: string | null;
  actionContractId: string | null;
  authorityEvidenceId: string | null;
  authorityEvidenceHash: string | null;
  authorityValidationStatus: string | null;
  commitBoundaryResult: string | null;
  irreversibilityBoundaryId: string | null;
  failedPredicates: Record<string, unknown>[];
  stalePredicates: Record<string, unknown>[];
  missingPredicates: Record<string, unknown>[];
  refusalBasis: string[];
  escalationBasis: string[];
  authorityCheckResult: Record<string, unknown> | null;
  constraintCheckResult: Record<string, unknown> | null;
  driftCheckResult: Record<string, unknown> | null;
  riskCheckResult: Record<string, unknown> | null;
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
  const [bindReceiptLookupError, setBindReceiptLookupError] = useState<string | null>(null);
  const [bindReceiptLookupLoading, setBindReceiptLookupLoading] = useState(false);
  const [bindReceiptIdFromQuery, setBindReceiptIdFromQuery] = useState<string | null>(null);
  const [decisionIdFromQuery, setDecisionIdFromQuery] = useState<string | null>(null);
  const [executionIntentIdFromQuery, setExecutionIntentIdFromQuery] = useState<string | null>(null);
  const [queryTraceStatus, setQueryTraceStatus] = useState<string | null>(null);
  const [bindReceiptLookupDetail, setBindReceiptLookupDetail] = useState<BindReceiptLookupDetail | null>(null);

  const bindReceiptBootstrappedRef = useRef(false);
  const queryAutoLoadStartedRef = useRef(false);

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
  const searchAbortRef = useRef<AbortController | null>(null);

  const matchesBindReceiptId = (item: TrustLogItem, bindReceiptId: string): boolean => {
    if (String(item.bind_receipt_id ?? "") === bindReceiptId) {
      return true;
    }

    if (
      item.metadata &&
      typeof item.metadata === "object" &&
      item.metadata !== null &&
      String((item.metadata as Record<string, unknown>).bind_receipt_id ?? "") === bindReceiptId
    ) {
      return true;
    }

    if (
      item.bind_receipt &&
      typeof item.bind_receipt === "object" &&
      item.bind_receipt !== null &&
      String((item.bind_receipt as Record<string, unknown>).bind_receipt_id ?? "") === bindReceiptId
    ) {
      return true;
    }

    return false;
  };
  const AUDIT_ARTIFACT_ID_PATTERN = /^[A-Za-z0-9._:-]{1,128}$/;

  const matchesDecisionId = (item: TrustLogItem, decisionId: string): boolean =>
    String(item.decision_id ?? "") === decisionId;

  const matchesExecutionIntentId = (item: TrustLogItem, executionIntentId: string): boolean => {
    if (String((item as Record<string, unknown>).execution_intent_id ?? "") === executionIntentId) {
      return true;
    }
    if (
      item.metadata &&
      typeof item.metadata === "object" &&
      item.metadata !== null &&
      String((item.metadata as Record<string, unknown>).execution_intent_id ?? "") === executionIntentId
    ) {
      return true;
    }
    if (
      item.bind_receipt &&
      typeof item.bind_receipt === "object" &&
      item.bind_receipt !== null &&
      String((item.bind_receipt as Record<string, unknown>).execution_intent_id ?? "") === executionIntentId
    ) {
      return true;
    }
    return false;
  };

  const isRecord = (value: unknown): value is Record<string, unknown> =>
    typeof value === "object" && value !== null;

  const asStringOrNull = (value: unknown): string | null => (typeof value === "string" ? value : null);

  const asRecordOrNull = (value: unknown): Record<string, unknown> | null => (isRecord(value) ? value : null);

  const asRecordArray = (value: unknown): Record<string, unknown>[] =>
    Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => isRecord(item)) : [];

  const asStringArray = (value: unknown): string[] =>
    Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];

  const parseBindReceiptLookupDetail = (
    payload: unknown,
    fallbackBindReceiptId: string,
  ): BindReceiptLookupDetail | null => {
    if (!isRecord(payload)) {
      return null;
    }
    const nested = asRecordOrNull(payload.bind_receipt);
    return {
      bindReceiptId:
        asStringOrNull(payload.bind_receipt_id) ??
        asStringOrNull(nested?.bind_receipt_id) ??
        fallbackBindReceiptId,
      executionIntentId:
        asStringOrNull(payload.execution_intent_id) ??
        asStringOrNull(nested?.execution_intent_id),
      finalOutcome:
        asStringOrNull(payload.bind_outcome) ??
        asStringOrNull(payload.final_outcome) ??
        asStringOrNull(nested?.final_outcome),
      bindFailureReason:
        asStringOrNull(payload.bind_failure_reason) ??
        asStringOrNull(payload.rollback_reason) ??
        asStringOrNull(payload.escalation_reason) ??
        asStringOrNull(nested?.bind_failure_reason) ??
        asStringOrNull(nested?.rollback_reason) ??
        asStringOrNull(nested?.escalation_reason),
      actionContractId:
        asStringOrNull(payload.action_contract_id) ??
        asStringOrNull(nested?.action_contract_id),
      authorityEvidenceId:
        asStringOrNull(payload.authority_evidence_id) ??
        asStringOrNull(nested?.authority_evidence_id),
      authorityEvidenceHash:
        asStringOrNull(payload.authority_evidence_hash) ??
        asStringOrNull(nested?.authority_evidence_hash),
      authorityValidationStatus:
        asStringOrNull(payload.authority_validation_status) ??
        asStringOrNull(nested?.authority_validation_status),
      commitBoundaryResult:
        asStringOrNull(payload.commit_boundary_result) ??
        asStringOrNull(nested?.commit_boundary_result),
      irreversibilityBoundaryId:
        asStringOrNull(payload.irreversibility_boundary_id) ??
        asStringOrNull(nested?.irreversibility_boundary_id),
      failedPredicates:
        asRecordArray(payload.failed_predicates)
        .concat(asRecordArray(nested?.failed_predicates)),
      stalePredicates:
        asRecordArray(payload.stale_predicates)
        .concat(asRecordArray(nested?.stale_predicates)),
      missingPredicates:
        asRecordArray(payload.missing_predicates)
        .concat(asRecordArray(nested?.missing_predicates)),
      refusalBasis: asStringArray(payload.refusal_basis).concat(asStringArray(nested?.refusal_basis)),
      escalationBasis: asStringArray(payload.escalation_basis).concat(asStringArray(nested?.escalation_basis)),
      authorityCheckResult:
        asRecordOrNull(payload.authority_check_result) ??
        asRecordOrNull(nested?.authority_check_result),
      constraintCheckResult:
        asRecordOrNull(payload.constraint_check_result) ??
        asRecordOrNull(nested?.constraint_check_result),
      driftCheckResult:
        asRecordOrNull(payload.drift_check_result) ??
        asRecordOrNull(nested?.drift_check_result),
      riskCheckResult:
        asRecordOrNull(payload.risk_check_result) ??
        asRecordOrNull(nested?.risk_check_result),
    };
  };

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
        item.bind_receipt_id,
        item.metadata &&
        typeof item.metadata === "object" &&
        item.metadata !== null
          ? (item.metadata as Record<string, unknown>).bind_receipt_id
          : undefined,
        item.bind_receipt &&
        typeof item.bind_receipt === "object" &&
        item.bind_receipt !== null
          ? (item.bind_receipt as Record<string, unknown>).bind_receipt_id
          : undefined,
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

  const bindReceiptFoundInTimeline = useMemo(() => {
    if (!bindReceiptIdFromQuery) {
      return false;
    }
    return sortedItems.some((item) => matchesBindReceiptId(item, bindReceiptIdFromQuery));
  }, [bindReceiptIdFromQuery, sortedItems]);

  const bindReceiptLookupSucceeded = useMemo(
    () => Boolean(bindReceiptIdFromQuery) && !bindReceiptLookupLoading && !bindReceiptLookupError,
    [bindReceiptIdFromQuery, bindReceiptLookupError, bindReceiptLookupLoading],
  );

  const bindReceiptTimelineMiss = useMemo(
    () => bindReceiptLookupSucceeded && !bindReceiptFoundInTimeline,
    [bindReceiptFoundInTimeline, bindReceiptLookupSucceeded],
  );

  const showBindReceiptFallback = useMemo(
    () => bindReceiptTimelineMiss && bindReceiptLookupDetail !== null,
    [bindReceiptLookupDetail, bindReceiptTimelineMiss],
  );

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

    // Cancel any in-flight search request before starting a new one
    searchAbortRef.current?.abort();
    const controller = new AbortController();
    searchAbortRef.current = controller;

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
        { signal: controller.signal },
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
        // Cancelled by a newer search call — silently drop the stale request
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

  useEffect(() => {
    if (bindReceiptBootstrappedRef.current) {
      return;
    }
    bindReceiptBootstrappedRef.current = true;

    const params = new URLSearchParams(window.location.search);
    const bindReceiptId = params.get("bind_receipt_id")?.trim() ?? "";
    const decisionId = params.get("decision_id")?.trim() ?? "";
    const executionIntentId = params.get("execution_intent_id")?.trim() ?? "";

    if (bindReceiptId) {
      if (!AUDIT_ARTIFACT_ID_PATTERN.test(bindReceiptId)) {
        setBindReceiptLookupDetail(null);
        setBindReceiptLookupError(
          t(
            "無効な bind_receipt_id が指定されました。",
            "Invalid bind_receipt_id query parameter.",
          ),
        );
        return;
      }

      setBindReceiptIdFromQuery(bindReceiptId);
      setCrossSearch({ query: bindReceiptId, field: "all" });

      const loadFromQuery = async (): Promise<void> => {
        setBindReceiptLookupLoading(true);
        setBindReceiptLookupError(null);
        try {
          const response = await veritasFetch(
            `/api/veritas/v1/governance/bind-receipts/${encodeURIComponent(bindReceiptId)}`,
          );

        if (response.status === 404) {
          setBindReceiptLookupDetail(null);
          setBindReceiptLookupError(
            t(
              "指定された bind receipt は見つかりませんでした。",
              "The requested bind receipt was not found.",
            ),
          );
          return;
        }

        if (!response.ok) {
          setBindReceiptLookupDetail(null);
          setBindReceiptLookupError(`HTTP ${response.status}: Failed to fetch bind receipt.`);
          return;
        }

        const payload: unknown = await response.json();
        setBindReceiptLookupDetail(parseBindReceiptLookupDetail(payload, bindReceiptId));
        await loadLogs(null, true);
      } catch {
        setBindReceiptLookupDetail(null);
        setBindReceiptLookupError(
          t(
            "ネットワークエラー: bind receipt 取得に失敗しました。",
            "Network error: failed to fetch bind receipt.",
          ),
        );
        } finally {
          setBindReceiptLookupLoading(false);
        }
      };

      void loadFromQuery();
      return;
    }

    if (decisionId) {
      if (!AUDIT_ARTIFACT_ID_PATTERN.test(decisionId)) {
        setBindReceiptLookupError(
          t("無効な decision_id が指定されました。", "Invalid decision_id query parameter."),
        );
        return;
      }
      setDecisionIdFromQuery(decisionId);
      setSelectedDecisionId(decisionId);
      setCrossSearch({ query: decisionId, field: "decision_id" });
      setQueryTraceStatus("pending");
      if (!queryAutoLoadStartedRef.current && items.length === 0) {
        queryAutoLoadStartedRef.current = true;
        void loadLogs(null, true);
      }
      return;
    }

    if (executionIntentId) {
      if (!AUDIT_ARTIFACT_ID_PATTERN.test(executionIntentId)) {
        setBindReceiptLookupError(
          t(
            "無効な execution_intent_id が指定されました。",
            "Invalid execution_intent_id query parameter.",
          ),
        );
        return;
      }
      setExecutionIntentIdFromQuery(executionIntentId);
      setCrossSearch({ query: executionIntentId, field: "all" });
      setQueryTraceStatus("pending");
      if (!queryAutoLoadStartedRef.current && items.length === 0) {
        queryAutoLoadStartedRef.current = true;
        void loadLogs(null, true);
      }
    }
  }, [items.length, loadLogs, t]);

  useEffect(() => {
    if (!bindReceiptIdFromQuery || sortedItems.length === 0) {
      return;
    }

    const matched = sortedItems.find((item) => matchesBindReceiptId(item, bindReceiptIdFromQuery));
    if (matched) {
      setSelected(matched);
      setDetailTab("related");
    }
  }, [bindReceiptIdFromQuery, sortedItems]);

  useEffect(() => {
    if (!decisionIdFromQuery || sortedItems.length === 0) {
      return;
    }
    const matched = sortedItems.find((item) => matchesDecisionId(item, decisionIdFromQuery));
    if (matched) {
      setSelected(matched);
      setDetailTab("related");
      setQueryTraceStatus("decision:matched");
      return;
    }
    setQueryTraceStatus("decision:not-found");
  }, [decisionIdFromQuery, sortedItems]);

  useEffect(() => {
    if (!executionIntentIdFromQuery || sortedItems.length === 0) {
      return;
    }
    const matched = sortedItems.find((item) => matchesExecutionIntentId(item, executionIntentIdFromQuery));
    if (matched) {
      setSelected(matched);
      setDetailTab("related");
      setQueryTraceStatus("execution-intent:matched");
      return;
    }
    setQueryTraceStatus("execution-intent:not-found");
  }, [executionIntentIdFromQuery, sortedItems]);

  /* ---------------------------------------------------------------- */
  /*  Return                                                           */
  /* ---------------------------------------------------------------- */

  return {
    items,
    cursor,
    hasMore,
    loading,
    error,
    bindReceiptLookupError,
    bindReceiptLookupLoading,
    bindReceiptIdFromQuery,
    bindReceiptFoundInTimeline,
    bindReceiptLookupDetail,
    bindReceiptLookupSucceeded,
    bindReceiptTimelineMiss,
    showBindReceiptFallback,
    decisionIdFromQuery,
    executionIntentIdFromQuery,
    queryTraceStatus,
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
