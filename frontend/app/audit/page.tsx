"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Card } from "@veritas/design-system";
import { veritasFetch } from "../../lib/api-client";
import {
  isRequestLogResponse,
  isTrustLogsResponse,
  type RequestLogResponse,
  type TrustLogItem,
} from "../../lib/api-validators";
import { useI18n } from "../../components/i18n-provider";
import {
  classifyChain,
  computeAuditSummary,
  buildHumanSummary,
  getString,
  shortHash,
  toPrettyJson,
  type AuditSummary,
  type ChainResult,
  type CrossSearchParams,
  type DetailTab,
  type ExportFormat,
  type RedactionMode,
  type RegulatoryReport,
  type SearchField,
  type VerificationStatus,
} from "./audit-types";

const PAGE_LIMIT = 50;

/* ------------------------------------------------------------------ */
/*  Status colors                                                      */
/* ------------------------------------------------------------------ */

const STATUS_COLORS: Record<VerificationStatus, string> = {
  verified: "text-success",
  broken: "text-danger",
  missing: "text-warning",
  orphan: "text-info",
};

const STATUS_BG: Record<VerificationStatus, string> = {
  verified: "bg-success/10 border-success/30",
  broken: "bg-danger/10 border-danger/30",
  missing: "bg-warning/10 border-warning/30",
  orphan: "bg-info/10 border-info/30",
};

const STATUS_DOT: Record<VerificationStatus, string> = {
  verified: "bg-success",
  broken: "bg-danger",
  missing: "bg-warning",
  orphan: "bg-info",
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function TrustLogExplorerPage(): JSX.Element {
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
  const [latestReport, setLatestReport] = useState<RegulatoryReport | null>(null);
  const [confirmPiiRisk, setConfirmPiiRisk] = useState(false);
  const [redactionMode, setRedactionMode] = useState<RedactionMode>("full");
  const [exportFormat, setExportFormat] = useState<ExportFormat>("json");

  const requestSearchNonceRef = useRef(0);

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

  /* -- export helpers ---------------------------------------------- */

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

  const verifySelectedDecision = (): void => {
    if (!selectedDecisionEntry) {
      setVerificationMessage(
        t("意思決定IDを選択してください。", "Please select a decision ID."),
      );
      return;
    }
    const idx = sortedItems.findIndex((item) => item === selectedDecisionEntry);
    const previous = idx >= 0 ? sortedItems[idx + 1] ?? null : null;
    const result = classifyChain(selectedDecisionEntry, previous);
    if (result.status === "verified") {
      setVerificationMessage("TAMPER-PROOF ✅");
      return;
    }
    setVerificationMessage(`${result.status.toUpperCase()}: ${result.reason}`);
  };

  const createRegulatoryReport = (): RegulatoryReport | null => {
    setReportError(null);
    if (!confirmPiiRisk) {
      setReportError(
        t(
          "PII/metadata warning を確認してください。",
          "Please acknowledge the PII/metadata warning.",
        ),
      );
      return null;
    }
    if (!reportStartDate || !reportEndDate) {
      setReportError(
        t("期間を指定してください。", "Please select both start and end dates."),
      );
      return null;
    }
    const start = new Date(`${reportStartDate}T00:00:00.000Z`).getTime();
    const end = new Date(`${reportEndDate}T23:59:59.999Z`).getTime();
    const periodItems = sortedItems.filter((item) => {
      const stamp = new Date(item.created_at ?? "").getTime();
      return Number.isFinite(stamp) && stamp >= start && stamp <= end;
    });
    if (periodItems.length === 0) {
      setReportError(
        t(
          "指定期間にデータがありません。",
          "No logs found for the selected period.",
        ),
      );
      return null;
    }

    const summary = computeAuditSummary(periodItems);

    const report: RegulatoryReport = {
      generatedAt: new Date().toISOString(),
      totalEntries: summary.total,
      verified: summary.verified,
      broken: summary.broken,
      missing: summary.missing,
      orphan: summary.orphan,
      mismatchLinks: summary.broken,
      brokenCount: summary.broken,
      redactionMode,
      policyVersions: summary.policyVersions,
    };
    setLatestReport(report);
    return report;
  };

  const downloadJsonReport = (): void => {
    const report = createRegulatoryReport();
    if (!report) return;
    const reportBlob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const objectUrl = URL.createObjectURL(reportBlob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `audit-report-${reportStartDate}-${reportEndDate}.json`;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  };

  /**
   * Builds a printable report using DOM APIs only to avoid HTML injection risks.
   */
  const generatePdfReport = (): void => {
    const report = createRegulatoryReport();
    if (!report) return;
    const printWindow = window.open(
      "",
      "_blank",
      "noopener,noreferrer,width=900,height=700",
    );
    if (!printWindow) {
      setReportError(
        t(
          "PDFウィンドウを開けませんでした。",
          "Failed to open PDF print window.",
        ),
      );
      return;
    }
    const doc = printWindow.document;
    const title = doc.createElement("h1");
    title.textContent = "Regulatory Report Generator";
    const warning = doc.createElement("p");
    warning.textContent =
      "Security note: Report may include PII and sensitive metadata.";
    const redactNote = doc.createElement("p");
    redactNote.textContent = `Redaction mode: ${report.redactionMode}`;
    doc.body.appendChild(title);
    doc.body.appendChild(warning);
    doc.body.appendChild(redactNote);
    doc.body.appendChild(doc.createTextNode(JSON.stringify(report, null, 2)));
    doc.close();
    printWindow.focus();
    printWindow.print();
  };

  const handleExport = (): void => {
    if (exportFormat === "pdf") {
      generatePdfReport();
    } else {
      downloadJsonReport();
    }
  };

  const loadLogs = async (
    nextCursor: string | null,
    replace: boolean,
  ): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_LIMIT) });
      if (nextCursor) params.set("cursor", nextCursor);
      const response = await veritasFetch(
        `/api/veritas/v1/trust/logs?${params.toString()}`,
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
      setLoading(false);
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
  /*  Render helpers                                                   */
  /* ---------------------------------------------------------------- */

  const SEARCH_FIELDS: { value: SearchField; label: string }[] = [
    { value: "all", label: t("すべて", "All fields") },
    { value: "decision_id", label: "decision_id" },
    { value: "request_id", label: "request_id" },
    { value: "replay_id", label: "replay_id" },
    { value: "policy_version", label: "policy_version" },
  ];

  const DETAIL_TABS: { value: DetailTab; label: string }[] = [
    { value: "summary", label: t("サマリー", "Summary") },
    { value: "metadata", label: t("メタデータ", "Metadata") },
    { value: "hash", label: t("ハッシュ", "Hash") },
    { value: "related", label: t("関連ID", "Related") },
    { value: "raw", label: "Raw JSON" },
  ];

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="space-y-6">
      {/* =========================================================== */}
      {/* Req 7: Empty-state hero / page purpose                       */}
      {/* =========================================================== */}
      <Card
        title="TrustLog Explorer"
        description={t(
          "ハッシュチェーン監査証跡の人間検証・エクスポート",
          "Hash-chained audit trail for human verification and export",
        )}
        variant="glass"
        accent="info"
      >
        <div className="space-y-1 text-xs text-muted-foreground">
          <p>
            {t(
              "この画面では、AI意思決定のハッシュチェーン整合性の検証、タイムライン上での監査対象の特定、decision / replay / metadata の追跡、安全なエクスポートを行えます。",
              "Use this page to verify hash-chain integrity of AI decisions, identify audit targets on the timeline, trace decision / replay / metadata links, and export evidence safely.",
            )}
          </p>
          {items.length === 0 && (
            <p className="mt-2 rounded border border-info/20 bg-info/5 px-3 py-2">
              {t(
                "まず「最新ログを読み込み」で監査ログを取得してください。読み込み後、タイムラインにエントリが表示され、ハッシュチェーン検証・横断検索・エクスポートが可能になります。",
                "Start by clicking \"Load latest logs\" to fetch audit entries. Once loaded, the timeline will populate and you can verify hash chains, cross-search, and export evidence.",
              )}
            </p>
          )}
        </div>
      </Card>

      {/* =========================================================== */}
      {/* Connection                                                    */}
      {/* =========================================================== */}
      <Card
        title={t("接続・読み込み", "Connection")}
        titleSize="sm"
        variant="elevated"
      >
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm"
            disabled={loading}
            onClick={() => void loadLogs(null, true)}
          >
            {loading
              ? t("読み込み中...", "Loading...")
              : t("最新ログを読み込み", "Load latest logs")}
          </button>
          <button
            type="button"
            className="rounded-lg border border-border px-4 py-2 text-sm"
            disabled={loading || !hasMore || !cursor}
            onClick={() => void loadLogs(cursor, false)}
          >
            {t("追加読み込み", "Load more")}
          </button>
        </div>
      </Card>

      {/* =========================================================== */}
      {/* request_id search                                            */}
      {/* =========================================================== */}
      <Card
        title={t("request_id 検索", "request_id Search")}
        titleSize="sm"
        variant="elevated"
      >
        <div className="flex gap-2">
          <input
            aria-label={t("リクエストIDで検索", "Search by request ID")}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
            value={requestId}
            onChange={(e) => setRequestId(e.target.value)}
            placeholder="request_id"
          />
          <button
            type="button"
            className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm"
            disabled={loading}
            onClick={() => void searchByRequestId()}
          >
            {t("検索", "Search")}
          </button>
        </div>
        {requestResult ? (
          <p className="mt-2 text-xs">
            count: {requestResult.count} / chain_ok:{" "}
            {String(requestResult.chain_ok)} / result:{" "}
            {requestResult.verification_result}
          </p>
        ) : null}
      </Card>

      {/* =========================================================== */}
      {/* Req 5: Cross-search with field selector                      */}
      {/* =========================================================== */}
      <Card
        title={t("横断検索", "Cross-search")}
        titleSize="sm"
        variant="elevated"
      >
        <div className="flex gap-2">
          <select
            aria-label={t("検索フィールド", "Search field")}
            className="rounded-lg border border-border px-2 py-2 text-sm"
            value={crossSearch.field}
            onChange={(e) =>
              setCrossSearch((prev) => ({
                ...prev,
                field: e.target.value as SearchField,
              }))
            }
          >
            {SEARCH_FIELDS.map((f) => (
              <option key={f.value} value={f.value}>
                {f.label}
              </option>
            ))}
          </select>
          <input
            aria-label="cross-search"
            className="w-full rounded-lg border border-border px-3 py-2 text-sm"
            value={crossSearch.query}
            onChange={(e) =>
              setCrossSearch((prev) => ({ ...prev, query: e.target.value }))
            }
            placeholder={t(
              "decision_id / request_id / replay_id / policy_version",
              "decision_id / request_id / replay_id / policy_version",
            )}
          />
        </div>
        {crossSearch.query && (
          <p className="mt-1 text-xs text-muted-foreground">
            {t("一致", "Matches")}: {filteredItems.length}
          </p>
        )}
      </Card>

      {error ? (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          {error}
        </p>
      ) : null}

      {/* =========================================================== */}
      {/* Req 1: Enhanced Audit Summary                                */}
      {/* =========================================================== */}
      <Card title="Audit Summary" titleSize="sm" variant="elevated">
        {filteredItems.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t(
              "ログを読み込むと、ここに全体の監査サマリーが表示されます。",
              "Load logs to see the overall audit summary here.",
            )}
          </p>
        ) : (
          <div className="space-y-3">
            {/* Status bar */}
            <div className="grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-6">
              <div className="rounded border border-border px-3 py-2 text-center">
                <p className="text-lg font-semibold">{auditSummary.total}</p>
                <p className="text-2xs text-muted-foreground">
                  {t("全エントリ", "Total")}
                </p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.verified}`}
              >
                <p className="text-lg font-semibold text-success">
                  {auditSummary.verified}
                </p>
                <p className="text-2xs text-muted-foreground">Verified</p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.broken}`}
              >
                <p className="text-lg font-semibold text-danger">
                  {auditSummary.broken}
                </p>
                <p className="text-2xs text-muted-foreground">Broken</p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.missing}`}
              >
                <p className="text-lg font-semibold text-warning">
                  {auditSummary.missing}
                </p>
                <p className="text-2xs text-muted-foreground">Missing</p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.orphan}`}
              >
                <p className="text-lg font-semibold text-info">
                  {auditSummary.orphan}
                </p>
                <p className="text-2xs text-muted-foreground">Orphan</p>
              </div>
              <div className="rounded border border-border px-3 py-2 text-center">
                <p className="text-lg font-semibold">
                  {auditSummary.replayLinked}
                </p>
                <p className="text-2xs text-muted-foreground">
                  {t("リプレイ連携", "Replay Linked")}
                </p>
              </div>
            </div>

            {/* Policy version distribution */}
            {Object.keys(auditSummary.policyVersions).length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold">
                  {t("ポリシーバージョン分布", "Policy Version Distribution")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(auditSummary.policyVersions).map(
                    ([version, count]) => (
                      <span
                        key={version}
                        className="rounded border border-border px-2 py-0.5 font-mono text-2xs"
                      >
                        {version}: {count}
                      </span>
                    ),
                  )}
                </div>
              </div>
            )}

            {/* Integrity bar */}
            {auditSummary.total > 0 && (
              <div>
                <div className="flex h-2 overflow-hidden rounded-full">
                  {auditSummary.verified > 0 && (
                    <div
                      className="bg-success"
                      style={{
                        width: `${(auditSummary.verified / auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                  {auditSummary.broken > 0 && (
                    <div
                      className="bg-danger"
                      style={{
                        width: `${(auditSummary.broken / auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                  {auditSummary.missing > 0 && (
                    <div
                      className="bg-warning"
                      style={{
                        width: `${(auditSummary.missing / auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                  {auditSummary.orphan > 0 && (
                    <div
                      className="bg-info"
                      style={{
                        width: `${(auditSummary.orphan / auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                </div>
                <p className="mt-1 text-2xs text-muted-foreground">
                  {t("チェーン整合率", "Chain integrity")}:{" "}
                  {Math.round(
                    (auditSummary.verified / auditSummary.total) * 100,
                  )}
                  %
                </p>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* =========================================================== */}
      {/* Req 2: Enhanced Timeline                                     */}
      {/* =========================================================== */}
      <Card title="Timeline" titleSize="md" variant="elevated">
        <div className="mb-2 flex items-center gap-2">
          <label htmlFor="stage-filter" className="text-xs">
            Stage
          </label>
          <select
            id="stage-filter"
            value={stageFilter}
            onChange={(e) => setStageFilter(e.target.value)}
            className="rounded border border-border px-2 py-1 text-xs"
          >
            {stageOptions.map((stage) => (
              <option key={stage} value={stage}>
                {stage}
              </option>
            ))}
          </select>
          <span className="ml-auto text-xs">
            {t("表示件数", "Visible")}: {filteredItems.length}
          </span>
        </div>
        {filteredItems.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t(
              "監査対象が未読込です。request_id/decision_id・ハッシュ整合・リプレイ関連をここで確認できます。",
              "No logs loaded yet. This timeline verifies request/decision IDs, hash chain, and replay linkage.",
            )}
          </p>
        ) : null}

        {/* Column header */}
        {filteredItems.length > 0 && (
          <div className="mb-1 grid grid-cols-2 gap-1 px-3 text-2xs font-semibold text-muted-foreground md:grid-cols-7">
            <span>{t("重要度", "Severity")}</span>
            <span>Stage</span>
            <span>{t("タイムスタンプ", "Timestamp")}</span>
            <span>request_id</span>
            <span>decision_id</span>
            <span>{t("チェーン", "Chain")}</span>
            <span>Replay</span>
          </div>
        )}

        <ol className="space-y-1">
          {filteredItems.map((item, index) => {
            const chain = classifyChain(
              item,
              filteredItems[index + 1] ?? null,
            );
            const isSelected = selected === item;
            const timelineKey = [
              item.request_id ?? "unknown",
              String(item.decision_id ?? "no-decision"),
              item.created_at ?? "no-timestamp",
              item.sha256 ?? "no-sha",
              item.sha256_prev ?? "no-prev-sha",
            ].join("-");
            return (
              <li key={timelineKey}>
                <button
                  type="button"
                  onClick={() => {
                    setSelected(item);
                    setDetailTab("summary");
                  }}
                  className={`w-full rounded border px-3 py-2 text-left text-xs transition-colors ${
                    isSelected
                      ? "border-primary/50 bg-primary/5"
                      : "border-border hover:bg-muted/30"
                  }`}
                >
                  <div className="grid grid-cols-2 gap-1 md:grid-cols-7">
                    <span className="font-medium">
                      {getString(item, "severity")}
                    </span>
                    <span>{item.stage ?? "UNKNOWN"}</span>
                    <span className="font-mono text-2xs">
                      {item.created_at ?? "-"}
                    </span>
                    <span className="truncate font-mono text-2xs">
                      {item.request_id ?? "-"}
                    </span>
                    <span className="truncate font-mono text-2xs">
                      {String(item.decision_id ?? "-")}
                    </span>
                    <span className="flex items-center gap-1">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT[chain.status]}`}
                      />
                      <span className={STATUS_COLORS[chain.status]}>
                        {chain.status}
                      </span>
                    </span>
                    <span className="text-2xs">
                      {typeof item.replay_id === "string" ? "linked" : "-"}
                    </span>
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>

      {/* =========================================================== */}
      {/* Req 3: Enhanced Selected Audit with tabs                     */}
      {/* =========================================================== */}
      <Card title="Selected Audit" titleSize="md" variant="elevated">
        {selected ? (
          <div className="space-y-3 text-xs">
            {/* Tab bar */}
            <div className="flex gap-1 border-b border-border pb-1">
              {DETAIL_TABS.map((tab) => (
                <button
                  key={tab.value}
                  type="button"
                  onClick={() => setDetailTab(tab.value)}
                  className={`rounded-t px-3 py-1.5 text-xs transition-colors ${
                    detailTab === tab.value
                      ? "border-b-2 border-primary bg-primary/5 font-semibold"
                      : "text-muted-foreground hover:bg-muted/20"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Tab: Summary */}
            {detailTab === "summary" && (
              <div className="space-y-3">
                <div
                  className={`rounded border p-3 ${selectedChain ? STATUS_BG[selectedChain.status] : "border-border"}`}
                >
                  <p className="text-sm font-medium">
                    {buildHumanSummary(selected)}
                  </p>
                  {selectedChain && (
                    <p className="mt-1">
                      <span className="font-semibold">
                        {t("チェーン状態", "Chain status")}:
                      </span>{" "}
                      <span className={STATUS_COLORS[selectedChain.status]}>
                        {selectedChain.status.toUpperCase()}
                      </span>{" "}
                      — {selectedChain.reason}
                    </p>
                  )}
                </div>
                <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
                  <p>
                    <strong>Stage:</strong> {selected.stage ?? "UNKNOWN"}
                  </p>
                  <p>
                    <strong>Status:</strong> {getString(selected, "status")}
                  </p>
                  <p>
                    <strong>Policy Version:</strong>{" "}
                    {getString(selected, "policy_version")}
                  </p>
                  <p>
                    <strong>Severity:</strong>{" "}
                    {getString(selected, "severity")}
                  </p>
                </div>
              </div>
            )}

            {/* Tab: Metadata */}
            {detailTab === "metadata" && (
              <div className="rounded border border-border p-3">
                <p className="mb-2 font-semibold">
                  {t("メタデータカード", "Metadata Card")}
                </p>
                <pre className="overflow-x-auto whitespace-pre-wrap rounded bg-muted/20 p-2 text-2xs">
                  {toPrettyJson(selected.metadata ?? {})}
                </pre>
              </div>
            )}

            {/* Tab: Hash */}
            {detailTab === "hash" && (
              <div className="space-y-2">
                <div className="grid gap-2 md:grid-cols-3">
                  <div className="rounded border border-border p-3 text-center">
                    <p className="text-2xs text-muted-foreground">
                      {t("前ログ", "Previous")}
                    </p>
                    <p className="mt-1 font-mono text-2xs">
                      {previousEntry
                        ? shortHash(previousEntry.sha256)
                        : t("なし", "none")}
                    </p>
                  </div>
                  <div
                    className={`rounded border p-3 text-center ${selectedChain ? STATUS_BG[selectedChain.status] : "border-border"}`}
                  >
                    <p className="text-2xs font-semibold">
                      {t("現在", "Current")}
                    </p>
                    <p className="mt-1 font-mono text-2xs">
                      {shortHash(selected.sha256)}
                    </p>
                    <p className="mt-0.5 font-mono text-2xs text-muted-foreground">
                      prev: {shortHash(selected.sha256_prev)}
                    </p>
                  </div>
                  <div className="rounded border border-border p-3 text-center">
                    <p className="text-2xs text-muted-foreground">
                      {t("次ログ", "Next")}
                    </p>
                    <p className="mt-1 font-mono text-2xs">
                      {nextEntry
                        ? shortHash(nextEntry.sha256)
                        : t("なし", "none")}
                    </p>
                  </div>
                </div>
                {selectedChain && selectedChain.status !== "verified" && (
                  <div
                    className={`rounded border p-3 ${STATUS_BG[selectedChain.status]}`}
                  >
                    <p className="font-semibold">
                      {selectedChain.status === "broken" &&
                        t(
                          "チェーン破損: ハッシュの不一致が検出されました。このエントリまたは前のエントリが改竄された可能性があります。",
                          "Chain broken: Hash mismatch detected. This entry or the previous one may have been tampered with.",
                        )}
                      {selectedChain.status === "missing" &&
                        t(
                          "ハッシュ欠損: 検証に必要なハッシュ値が存在しません。ログの欠落が考えられます。",
                          "Hash missing: A required hash value is absent. Log entries may be missing.",
                        )}
                      {selectedChain.status === "orphan" &&
                        t(
                          "孤立エントリ: 前のエントリが存在するにもかかわらず、sha256_prevが設定されていません。",
                          "Orphan entry: Previous entry exists but sha256_prev is not set on this entry.",
                        )}
                    </p>
                    <p className="mt-1 text-2xs">
                      {t("理由", "Reason")}: {selectedChain.reason}
                    </p>
                  </div>
                )}
              </div>
            )}

            {/* Tab: Related IDs */}
            {detailTab === "related" && (
              <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
                <p>
                  <strong>request_id:</strong>{" "}
                  <span className="font-mono">
                    {selected.request_id ?? "-"}
                  </span>
                </p>
                <p>
                  <strong>decision_id:</strong>{" "}
                  <span className="font-mono">
                    {String(selected.decision_id ?? "-")}
                  </span>
                </p>
                <p>
                  <strong>replay_id:</strong>{" "}
                  {typeof selected.replay_id === "string" ? (
                    <a
                      className="font-mono underline"
                      href={`/replay?replay_id=${encodeURIComponent(selected.replay_id)}`}
                    >
                      {selected.replay_id}
                    </a>
                  ) : (
                    "-"
                  )}
                </p>
                <p>
                  <strong>policy_version:</strong>{" "}
                  <span className="font-mono">
                    {getString(selected, "policy_version")}
                  </span>
                </p>
              </div>
            )}

            {/* Tab: Raw JSON */}
            {detailTab === "raw" && (
              <details open>
                <summary className="cursor-pointer font-semibold">
                  {t("JSON 展開", "Expand JSON")}
                </summary>
                <pre className="mt-2 overflow-x-auto rounded border border-border bg-muted/20 p-3">
                  {toPrettyJson(selected)}
                </pre>
              </details>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            {t(
              "タイムラインからログを選択すると、ここに詳細が表示されます。サマリー・メタデータ・ハッシュ検証・関連ID・生JSONの各タブで確認できます。",
              "Select a log from the timeline to see details. Tabs include summary, metadata, hash verification, related IDs, and raw JSON.",
            )}
          </p>
        )}
      </Card>

      {/* =========================================================== */}
      {/* Req 4: Enhanced Hash Chain Verification                      */}
      {/* =========================================================== */}
      <Card
        title={t(
          "TrustLog インタラクティブ検証",
          "TrustLog Interactive Verification",
        )}
        titleSize="md"
        variant="elevated"
        accent="success"
      >
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <select
              aria-label={t(
                "検証対象の意思決定ID",
                "Decision ID for verification",
              )}
              className="rounded border border-border px-2 py-1 text-xs"
              value={selectedDecisionId}
              onChange={(e) => setSelectedDecisionId(e.target.value)}
            >
              <option value="">
                {t("意思決定IDを選択", "Select a decision ID")}
              </option>
              {decisionIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="rounded border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs"
              onClick={verifySelectedDecision}
            >
              {t("ハッシュチェーン検証", "Verify hash chain")}
            </button>
          </div>
          {verificationMessage ? (
            <p className="text-xs">{verificationMessage}</p>
          ) : null}
          <div className="flex flex-wrap gap-2 text-2xs">
            <span className="flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT.verified}`} />
              verified
            </span>
            <span className="flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT.broken}`} />
              broken
            </span>
            <span className="flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT.missing}`} />
              missing
            </span>
            <span className="flex items-center gap-1">
              <span className={`inline-block h-2 w-2 rounded-full ${STATUS_DOT.orphan}`} />
              orphan
            </span>
          </div>
        </div>
      </Card>

      {/* =========================================================== */}
      {/* Req 6: Enhanced Export UX                                     */}
      {/* =========================================================== */}
      <Card
        title={t(
          "第三者監査用エクスポート",
          "Regulatory Report Generator",
        )}
        titleSize="md"
        variant="elevated"
        accent="warning"
      >
        <div className="space-y-4 text-sm">
          {/* Period selection */}
          <div>
            <p className="mb-1 text-xs font-semibold">
              {t("対象期間", "Export Period")}
            </p>
            <div className="grid gap-3 md:grid-cols-2">
              <input
                aria-label={t("監査レポート開始日", "Audit report start date")}
                type="date"
                value={reportStartDate}
                onChange={(e) => setReportStartDate(e.target.value)}
                className="rounded border border-border px-3 py-2"
              />
              <input
                aria-label={t("監査レポート終了日", "Audit report end date")}
                type="date"
                value={reportEndDate}
                onChange={(e) => setReportEndDate(e.target.value)}
                className="rounded border border-border px-3 py-2"
              />
            </div>
            {reportStartDate && reportEndDate && (
              <p className="mt-1 text-xs text-muted-foreground">
                {t("エクスポート対象", "Export target")}: {exportTargetCount}{" "}
                {t("件", "entries")}
              </p>
            )}
          </div>

          {/* Redaction mode */}
          <div>
            <p className="mb-1 text-xs font-semibold">
              {t("墨消しモード", "Redaction Mode")}
            </p>
            <div className="flex gap-3 text-xs">
              {(
                [
                  {
                    value: "full" as const,
                    label: t("完全出力", "Full"),
                    desc: t(
                      "すべてのフィールドを含む",
                      "Includes all fields",
                    ),
                  },
                  {
                    value: "redacted" as const,
                    label: t("墨消し", "Redacted"),
                    desc: t(
                      "PII関連フィールドを除外",
                      "PII fields removed",
                    ),
                  },
                  {
                    value: "metadata-only" as const,
                    label: t("メタデータのみ", "Metadata only"),
                    desc: t(
                      "監査メタデータのみ",
                      "Audit metadata only",
                    ),
                  },
                ] as const
              ).map((opt) => (
                <label key={opt.value} className="flex items-start gap-1.5">
                  <input
                    type="radio"
                    name="redaction"
                    value={opt.value}
                    checked={redactionMode === opt.value}
                    onChange={() => setRedactionMode(opt.value)}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">{opt.label}</span>
                    <br />
                    <span className="text-2xs text-muted-foreground">
                      {opt.desc}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </div>

          {/* Format selection */}
          <div>
            <p className="mb-1 text-xs font-semibold">
              {t("出力形式", "Export Format")}
            </p>
            <div className="flex gap-4 text-xs">
              <label className="flex items-start gap-1.5">
                <input
                  type="radio"
                  name="exportFormat"
                  value="json"
                  checked={exportFormat === "json"}
                  onChange={() => setExportFormat("json")}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">JSON</span>
                  <br />
                  <span className="text-2xs text-muted-foreground">
                    {t(
                      "機械可読形式。APIやスクリプトでの処理に最適",
                      "Machine-readable. Best for API and script processing",
                    )}
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-1.5">
                <input
                  type="radio"
                  name="exportFormat"
                  value="pdf"
                  checked={exportFormat === "pdf"}
                  onChange={() => setExportFormat("pdf")}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">PDF</span>
                  <br />
                  <span className="text-2xs text-muted-foreground">
                    {t(
                      "印刷用。第三者監査提出に適した形式",
                      "Printable. Suitable for third-party audit submission",
                    )}
                  </span>
                </span>
              </label>
            </div>
          </div>

          {/* PII acknowledgement */}
          <div className="rounded border border-warning/30 bg-warning/5 p-3">
            <label className="flex items-start gap-2 text-xs">
              <input
                type="checkbox"
                checked={confirmPiiRisk}
                onChange={(e) => setConfirmPiiRisk(e.target.checked)}
                className="mt-0.5"
              />
              <span>
                {t(
                  "PII/metadata warning を理解し、社内ポリシーに従って取り扱います。",
                  "I acknowledge PII/metadata warning and will handle exports under policy.",
                )}
              </span>
            </label>
            <p className="mt-2 text-2xs text-warning">
              {t(
                "セキュリティ警告: エクスポートにはPII（個人識別情報）や監査メタデータが含まれる可能性があります。社内の情報セキュリティポリシーに従い、安全に取り扱ってください。",
                "Security warning: Exports may include PII (personally identifiable information) and audit metadata. Handle according to your organization's information security policy.",
              )}
            </p>
          </div>

          {/* Export button */}
          <button
            type="button"
            className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm"
            onClick={handleExport}
          >
            {exportFormat === "json"
              ? t("JSON生成", "Generate JSON")
              : t("PDF生成", "Generate PDF")}
          </button>

          {reportError ? (
            <p className="text-xs text-warning">{reportError}</p>
          ) : null}
          {latestReport ? (
            <div className="rounded border border-border p-2 text-xs">
              <p>
                entries: {latestReport.totalEntries} / verified:{" "}
                {latestReport.verified} / broken: {latestReport.broken} /
                missing: {latestReport.missing} / orphan:{" "}
                {latestReport.orphan} / mismatches: {latestReport.mismatchLinks}
              </p>
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
