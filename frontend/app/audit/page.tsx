"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Card } from "@veritas/design-system";
import { veritasFetch } from "../../lib/api-client";
import { isRequestLogResponse, isTrustLogsResponse, type RequestLogResponse, type TrustLogItem } from "../../lib/api-validators";
import { useI18n } from "../../components/i18n-provider";

const PAGE_LIMIT = 50;

type VerificationStatus = "verified" | "broken" | "missing" | "orphan";

interface RegulatoryReport {
  generatedAt: string;
  totalEntries: number;
  mismatchLinks: number;
  brokenCount: number;
}

interface ChainResult {
  status: VerificationStatus;
  reason: string;
}

function toPrettyJson(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

function shortHash(value: string | undefined): string {
  if (!value) {
    return "missing";
  }

  if (value.length <= 18) {
    return value;
  }

  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

function getString(item: TrustLogItem, key: string): string {
  const value = item[key];
  return typeof value === "string" ? value : "-";
}

/**
 * Builds a deterministic key for timeline rows without relying on array indices.
 */
function buildTimelineKey(item: TrustLogItem): string {
  const requestId = typeof item.request_id === "string" ? item.request_id : "unknown";
  const decisionId = typeof item.decision_id === "string" ? item.decision_id : "-";
  const timestamp = typeof item.created_at === "string" ? item.created_at : "-";
  const hash = typeof item.sha256 === "string" ? item.sha256 : "-";
  const prevHash = typeof item.sha256_prev === "string" ? item.sha256_prev : "-";
  return `${requestId}:${decisionId}:${timestamp}:${hash}:${prevHash}`;
}

/**
 * Classifies a single hash chain link for audit visualization.
 */
function classifyChain(item: TrustLogItem, previous: TrustLogItem | null): ChainResult {
  if (!item.sha256) {
    return { status: "missing", reason: "current sha256 missing" };
  }

  if (!item.sha256_prev) {
    return previous
      ? { status: "orphan", reason: "no sha256_prev while previous exists" }
      : { status: "verified", reason: "genesis entry" };
  }

  if (!previous?.sha256) {
    return { status: "missing", reason: "previous sha256 missing" };
  }

  if (item.sha256_prev !== previous.sha256) {
    return { status: "broken", reason: "sha256_prev does not match previous sha256" };
  }

  return { status: "verified", reason: "hash chain match" };
}

export default function TrustLogExplorerPage(): JSX.Element {
  const { t } = useI18n();
  const [cursor, setCursor] = useState<string | null>(null);
  const [items, setItems] = useState<TrustLogItem[]>([]);
  const [selected, setSelected] = useState<TrustLogItem | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [requestId, setRequestId] = useState("");
  const [requestResult, setRequestResult] = useState<RequestLogResponse | null>(null);
  const [stageFilter, setStageFilter] = useState("ALL");
  const [searchKey, setSearchKey] = useState("");
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const [verificationMessage, setVerificationMessage] = useState("");
  const [reportStartDate, setReportStartDate] = useState("");
  const [reportEndDate, setReportEndDate] = useState("");
  const [reportError, setReportError] = useState<string | null>(null);
  const [latestReport, setLatestReport] = useState<RegulatoryReport | null>(null);
  const [confirmPiiRisk, setConfirmPiiRisk] = useState(false);
  const requestSearchNonceRef = useRef(0);

  const sortedItems = useMemo(
    () => [...items].sort((a, b) => new Date(b.created_at ?? "").getTime() - new Date(a.created_at ?? "").getTime()),
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
    const query = searchKey.trim().toLowerCase();
    return sortedItems.filter((item) => {
      if (stageFilter !== "ALL" && item.stage !== stageFilter) {
        return false;
      }
      if (!query) {
        return true;
      }
      const decisionId = String(item.decision_id ?? "").toLowerCase();
      const request = String(item.request_id ?? "").toLowerCase();
      return request.includes(query) || decisionId.includes(query);
    });
  }, [searchKey, sortedItems, stageFilter]);

  const decisionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of sortedItems) {
      const decisionId = item.decision_id;
      const fallback = item.request_id;
      if (typeof decisionId === "string" && decisionId.length > 0) {
        ids.add(decisionId);
      } else if (typeof fallback === "string" && fallback.length > 0) {
        ids.add(fallback);
      }
    }
    return Array.from(ids).sort();
  }, [sortedItems]);

  const selectedDecisionEntry = useMemo(() => {
    if (!selectedDecisionId) {
      return null;
    }
    return sortedItems.find(
      (item) => item.decision_id === selectedDecisionId || item.request_id === selectedDecisionId,
    ) ?? null;
  }, [selectedDecisionId, sortedItems]);

  const selectedIndex = useMemo(
    () => (selected ? filteredItems.findIndex((item) => item === selected) : -1),
    [filteredItems, selected],
  );
  const previousEntry = selectedIndex >= 0 ? filteredItems[selectedIndex + 1] ?? null : null;
  const nextEntry = selectedIndex > 0 ? filteredItems[selectedIndex - 1] ?? null : null;

  const selectedChain = useMemo(
    () => (selected ? classifyChain(selected, previousEntry) : null),
    [previousEntry, selected],
  );

  const auditSummary = useMemo(() => {
    let mismatches = 0;
    let brokenCount = 0;
    for (let index = 0; index < filteredItems.length; index += 1) {
      const status = classifyChain(filteredItems[index], filteredItems[index + 1] ?? null).status;
      if (status === "broken") {
        mismatches += 1;
        brokenCount += 1;
      }
    }
    return { total: filteredItems.length, mismatches, brokenCount };
  }, [filteredItems]);

  const verifySelectedDecision = (): void => {
    if (!selectedDecisionEntry) {
      setVerificationMessage(t("意思決定IDを選択してください。", "Please select a decision ID."));
      return;
    }
    const selectedIndexInAll = sortedItems.findIndex((item) => item === selectedDecisionEntry);
    const previous = selectedIndexInAll >= 0 ? sortedItems[selectedIndexInAll + 1] ?? null : null;
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
      setReportError(t("PII/metadata warning を確認してください。", "Please acknowledge the PII/metadata warning."));
      return null;
    }
    if (!reportStartDate || !reportEndDate) {
      setReportError(t("期間を指定してください。", "Please select both start and end dates."));
      return null;
    }
    const start = new Date(`${reportStartDate}T00:00:00.000Z`).getTime();
    const end = new Date(`${reportEndDate}T23:59:59.999Z`).getTime();
    const periodItems = sortedItems.filter((item) => {
      const stamp = new Date(item.created_at ?? "").getTime();
      return Number.isFinite(stamp) && stamp >= start && stamp <= end;
    });
    if (periodItems.length === 0) {
      setReportError(t("指定期間にデータがありません。", "No logs found for the selected period."));
      return null;
    }

    const mismatchLinks = periodItems.reduce((count, item, index) => {
      const next = periodItems[index + 1] ?? null;
      return count + (classifyChain(item, next).status === "broken" ? 1 : 0);
    }, 0);

    const report: RegulatoryReport = {
      generatedAt: new Date().toISOString(),
      totalEntries: periodItems.length,
      mismatchLinks,
      brokenCount: mismatchLinks,
    };
    setLatestReport(report);
    return report;
  };

  const downloadJsonReport = (): void => {
    const report = createRegulatoryReport();
    if (!report) {
      return;
    }
    const reportBlob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
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
    if (!report) {
      return;
    }
    const printWindow = window.open("", "_blank", "noopener,noreferrer,width=900,height=700");
    if (!printWindow) {
      setReportError(t("PDFウィンドウを開けませんでした。", "Failed to open PDF print window."));
      return;
    }
    const title = printWindow.document.createElement("h1");
    title.textContent = "Regulatory Report Generator";
    const warning = printWindow.document.createElement("p");
    warning.textContent = "Security note: Report may include PII and sensitive metadata.";
    printWindow.document.body.appendChild(title);
    printWindow.document.body.appendChild(warning);
    printWindow.document.body.appendChild(printWindow.document.createTextNode(JSON.stringify(report, null, 2)));
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
  };

  const loadLogs = async (nextCursor: string | null, replace: boolean): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      const params = new URLSearchParams({ limit: String(PAGE_LIMIT) });
      if (nextCursor) {
        params.set("cursor", nextCursor);
      }
      const response = await veritasFetch(`/api/veritas/v1/trust/logs?${params.toString()}`);
      if (!response.ok) {
        setError(`HTTP ${response.status}: ${t("trust logs取得に失敗しました。", "Failed to fetch trust logs.")}`);
        return;
      }
      const payload: unknown = await response.json();
      if (!isTrustLogsResponse(payload)) {
        setError(t("レスポンス形式エラー: trust logs の形式が不正です。", "Response format error: trust logs payload is invalid."));
        return;
      }
      const nextItems = payload.items;
      setItems((prev) => (replace ? nextItems : [...prev, ...nextItems]));
      setCursor(payload.next_cursor);
      setHasMore(Boolean(payload.has_more));
      if (replace && nextItems.length > 0) {
        setSelected(nextItems[0]);
      }
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError(t("タイムアウト: trust logs 取得が時間内に完了しませんでした。", "Timeout: trust logs request did not complete in time."));
        return;
      }
      setError(t("ネットワークエラー: trust logs 取得に失敗しました。", "Network error: failed to fetch trust logs."));
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
      const response = await veritasFetch(`/api/veritas/v1/trust/${encodeURIComponent(value)}`);
      if (!response.ok) {
        setError(`HTTP ${response.status}: ${t("request_id 検索に失敗しました。", "Failed to search request_id.")}`);
        return;
      }
      const payload: unknown = await response.json();
      if (requestNonce !== requestSearchNonceRef.current) {
        return;
      }
      if (!isRequestLogResponse(payload)) {
        setError(t("レスポンス形式エラー: request_id 応答の形式が不正です。", "Response format error: request_id payload is invalid."));
        return;
      }
      setRequestResult(payload);
      if (payload.items.length > 0) {
        setSelected(payload.items[payload.items.length - 1]);
      }
    } catch (caught: unknown) {
      if (caught instanceof DOMException && caught.name === "AbortError") {
        setError(t("タイムアウト: request_id 検索が時間内に完了しませんでした。", "Timeout: request_id search did not complete in time."));
        return;
      }
      setError(t("ネットワークエラー: request_id 検索に失敗しました。", "Network error: failed to search request_id."));
    } finally {
      if (requestNonce === requestSearchNonceRef.current) {
        setLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!selected && filteredItems.length > 0) {
      setSelected(filteredItems[0]);
    }
  }, [filteredItems, selected]);

  return (
    <div className="space-y-6">
      <Card title="TrustLog Explorer" description="Hash-chained audit trail for human verification and export" variant="glass" accent="info">
        <p className="text-xs text-muted-foreground">{t("空状態でも監査できる項目を確認できます。", "Use this page to inspect timeline, chain validity, replay links, and export evidence.")}</p>
      </Card>

      <Card title={t("接続・読み込み", "Connection")} titleSize="sm" variant="elevated">
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm" disabled={loading} onClick={() => void loadLogs(null, true)}>{loading ? t("読み込み中...", "Loading...") : t("最新ログを読み込み", "Load latest logs")}</button>
          <button type="button" className="rounded-lg border border-border px-4 py-2 text-sm" disabled={loading || !hasMore || !cursor} onClick={() => void loadLogs(cursor, false)}>{t("追加読み込み", "Load more")}</button>
        </div>
      </Card>

      <Card title={t("request_id 検索", "request_id Search")} titleSize="sm" variant="elevated">
        <div className="flex gap-2">
          <input aria-label={t("リクエストIDで検索", "Search by request ID")} className="w-full rounded-lg border border-border px-3 py-2 text-sm" value={requestId} onChange={(event) => setRequestId(event.target.value)} placeholder="request_id" />
          <button type="button" className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm" disabled={loading} onClick={() => void searchByRequestId()}>{t("検索", "Search")}</button>
        </div>
        {requestResult ? <p className="mt-2 text-xs">count: {requestResult.count} / chain_ok: {String(requestResult.chain_ok)} / result: {requestResult.verification_result}</p> : null}
      </Card>

      <Card title={t("横断検索", "Cross-search")} titleSize="sm" variant="elevated">
        <input aria-label="cross-search" className="w-full rounded-lg border border-border px-3 py-2 text-sm" value={searchKey} onChange={(event) => setSearchKey(event.target.value)} placeholder="request_id / decision_id" />
      </Card>

      {error ? <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">{error}</p> : null}

      <Card title="Audit Summary" titleSize="sm" variant="elevated">
        <p className="text-xs">Entries: {auditSummary.total} / Chain mismatch: {auditSummary.mismatches} / Broken: {auditSummary.brokenCount}</p>
      </Card>

      <Card title="Timeline" titleSize="md" variant="elevated">
        <div className="mb-2 flex items-center gap-2">
          <label htmlFor="stage-filter" className="text-xs">Stage</label>
          <select id="stage-filter" value={stageFilter} onChange={(event) => setStageFilter(event.target.value)} className="rounded border border-border px-2 py-1 text-xs">
            {stageOptions.map((stage) => <option key={stage} value={stage}>{stage}</option>)}
          </select>
          <span className="ml-auto text-xs">{t("表示件数", "Visible")}: {filteredItems.length}</span>
        </div>
        {filteredItems.length === 0 ? <p className="text-xs text-muted-foreground">{t("監査対象が未読込です。request_id/decision_id・ハッシュ整合・リプレイ関連をここで確認できます。", "No logs loaded yet. This timeline verifies request/decision IDs, hash chain, and replay linkage.")}</p> : null}
        <ol className="space-y-2">
          {filteredItems.map((item, index) => {
            const chain = classifyChain(item, filteredItems[index + 1] ?? null);
            return (
              <li key={buildTimelineKey(item)}>
                <button type="button" onClick={() => setSelected(item)} className="w-full rounded border border-border px-3 py-2 text-left text-xs">
                  <div className="grid grid-cols-2 gap-1 md:grid-cols-6">
                    <span>{getString(item, "severity")}</span>
                    <span>{item.stage ?? "UNKNOWN"}</span>
                    <span>{getString(item, "status")}</span>
                    <span className="font-mono">{item.created_at ?? "-"}</span>
                    <span className="font-mono">req:{item.request_id ?? "-"}</span>
                    <span className={chain.status === "verified" ? "text-success" : chain.status === "broken" ? "text-danger" : "text-warning"}>{chain.status}</span>
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>

      <Card title="Selected Audit" titleSize="md" variant="elevated">
        {selected ? (
          <div className="space-y-3 text-xs">
            <div className="grid gap-2 rounded border border-border p-3 md:grid-cols-2">
              <p><strong>Summary:</strong> {`Stage ${selected.stage ?? "UNKNOWN"} returned ${getString(selected, "status")} for request ${selected.request_id ?? "-"}.`}</p>
              <p><strong>Policy Version:</strong> {getString(selected, "policy_version")}</p>
              <p><strong>Metadata:</strong> {toPrettyJson(selected.metadata ?? {})}</p>
              <p><strong>Replay report:</strong> {typeof selected.replay_id === "string" ? <a className="underline" href={`/replay?replay_id=${encodeURIComponent(selected.replay_id)}`}>{selected.replay_id}</a> : "-"}</p>
              <p><strong>Hash:</strong> {shortHash(selected.sha256)} / prev {shortHash(selected.sha256_prev)}</p>
              <p><strong>Chain:</strong> {selectedChain?.status ?? "-"}</p>
            </div>
            <div className="rounded border border-border p-3">
              <p><strong>Previous log:</strong> {previousEntry ? shortHash(previousEntry.sha256) : "-"}</p>
              <p><strong>Next log:</strong> {nextEntry ? shortHash(nextEntry.sha256) : "-"}</p>
            </div>
            <details open>
              <summary className="cursor-pointer font-semibold">{t("JSON 展開", "Expand JSON")}</summary>
              <pre className="mt-2 overflow-x-auto rounded border border-border bg-muted/20 p-3">{toPrettyJson(selected)}</pre>
            </details>
          </div>
        ) : <p className="text-sm text-muted-foreground">{t("ログを選択してください。", "Select a log.")}</p>}
      </Card>

      <Card title={t("TrustLog インタラクティブ検証", "TrustLog Interactive Verification")} titleSize="md" variant="elevated" accent="success">
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <select className="rounded border border-border px-2 py-1 text-xs" value={selectedDecisionId} onChange={(event) => setSelectedDecisionId(event.target.value)}>
              <option value="">{t("意思決定IDを選択", "Select a decision ID")}</option>
              {decisionIds.map((id) => <option key={id} value={id}>{id}</option>)}
            </select>
            <button type="button" className="rounded border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs" onClick={verifySelectedDecision}>{t("ハッシュチェーン検証", "Verify hash chain")}</button>
          </div>
          {verificationMessage ? <p className="text-xs">{verificationMessage}</p> : null}
          <p className="text-xs text-muted-foreground">verified / broken / missing / orphan</p>
        </div>
      </Card>

      <Card title={t("第三者監査用エクスポート", "Regulatory Report Generator")} titleSize="md" variant="elevated" accent="warning">
        <div className="space-y-3 text-sm">
          <div className="grid gap-3 md:grid-cols-2">
            <input type="date" value={reportStartDate} onChange={(event) => setReportStartDate(event.target.value)} className="rounded border border-border px-3 py-2" />
            <input type="date" value={reportEndDate} onChange={(event) => setReportEndDate(event.target.value)} className="rounded border border-border px-3 py-2" />
          </div>
          <label className="flex items-start gap-2 text-xs">
            <input type="checkbox" checked={confirmPiiRisk} onChange={(event) => setConfirmPiiRisk(event.target.checked)} />
            <span>{t("PII/metadata warning を理解し、社内ポリシーに従って取り扱います。", "I acknowledge PII/metadata warning and will handle exports under policy.")}</span>
          </label>
          <div className="flex gap-2">
            <button type="button" className="rounded border border-primary/40 bg-primary/10 px-4 py-2 text-sm" onClick={downloadJsonReport}>{t("JSON生成", "Generate JSON")}</button>
            <button type="button" className="rounded border border-primary/40 bg-primary/10 px-4 py-2 text-sm" onClick={generatePdfReport}>{t("PDF生成", "Generate PDF")}</button>
          </div>
          {reportError ? <p className="text-xs text-warning">{reportError}</p> : null}
          {latestReport ? <p className="text-xs">entries: {latestReport.totalEntries} / mismatches: {latestReport.mismatchLinks}</p> : null}
          <p className="text-xs text-warning">{t("セキュリティ警告: 出力にはPIIや監査メタデータが含まれる可能性があります。", "Security warning: export may include PII and audit metadata.")}</p>
        </div>
      </Card>
    </div>
  );
}
