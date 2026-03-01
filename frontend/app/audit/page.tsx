"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@veritas/design-system";
import { isRequestLogResponse, isTrustLogsResponse, type RequestLogResponse, type TrustLogItem } from "../../lib/api-validators";
import { useI18n } from "../../components/i18n-provider";

const PAGE_LIMIT = 50;
const FETCH_TIMEOUT_MS = 15_000;

/**
 * Fetches an endpoint with an explicit timeout budget.
 */
async function fetchWithTimeout(input: RequestInfo | URL, init: RequestInit = {}, timeoutMs = FETCH_TIMEOUT_MS): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function toPrettyJson(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function shortHash(value: string | undefined): string {
  if (!value) {
    return "missing";
  }

  if (value.length <= 16) {
    return value;
  }

  return `${value.slice(0, 10)}...${value.slice(-6)}`;
}

type VerificationStatus = "idle" | "running" | "pass" | "fail";

interface ReportPeriod {
  startDate: string;
  endDate: string;
}

interface StageSummary {
  stage: string;
  count: number;
  passCount: number;
}

interface RegulatoryReport {
  generatedAt: string;
  period: ReportPeriod;
  totalEntries: number;
  totalDecisionIds: number;
  pipelineStageSummary: StageSummary[];
  fujiGate: {
    totalEvaluations: number;
    rejected: number;
    rejectionRate: number;
  };
  trustLogIntegrity: {
    checkedLinks: number;
    mismatchLinks: number;
    chainIntact: boolean;
  };
}

/**
 * Returns true if a log item is inside a date range (inclusive).
 */
function isWithinPeriod(item: TrustLogItem, startDate: string, endDate: string): boolean {
  if (!item.created_at) {
    return false;
  }

  const createdAt = new Date(item.created_at);
  const start = startDate ? new Date(`${startDate}T00:00:00.000Z`) : null;
  const end = endDate ? new Date(`${endDate}T23:59:59.999Z`) : null;

  if (Number.isNaN(createdAt.getTime())) {
    return false;
  }

  if (start && createdAt < start) {
    return false;
  }

  if (end && createdAt > end) {
    return false;
  }

  return true;
}

/**
 * Heuristically detects whether a trust log entry indicates a gate rejection.
 */
function isRejectedEntry(item: TrustLogItem): boolean {
  const status = String(item.status ?? item.result ?? item.verdict ?? "").toLowerCase();
  return ["deny", "denied", "reject", "rejected", "blocked"].includes(status);
}

/**
 * Heuristically detects whether a trust log entry indicates a successful pass.
 */
function isPassedEntry(item: TrustLogItem): boolean {
  const status = String(item.status ?? item.result ?? item.verdict ?? "").toLowerCase();
  return ["pass", "passed", "allow", "allowed", "approved", "ok"].includes(status);
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
  const [selectedDecisionId, setSelectedDecisionId] = useState("");
  const [verificationStatus, setVerificationStatus] = useState<VerificationStatus>("idle");
  const [verificationMessage, setVerificationMessage] = useState<string | null>(null);
  const [animationStep, setAnimationStep] = useState(0);
  const [reportStartDate, setReportStartDate] = useState("");
  const [reportEndDate, setReportEndDate] = useState("");
  const [reportError, setReportError] = useState<string | null>(null);
  const [latestReport, setLatestReport] = useState<RegulatoryReport | null>(null);

  const stageOptions = useMemo(() => {
    const stages = new Set<string>();
    for (const item of items) {
      const stage = typeof item.stage === "string" ? item.stage : "UNKNOWN";
      stages.add(stage);
    }
    return ["ALL", ...Array.from(stages).sort()];
  }, [items]);

  const filteredItems = useMemo(() => {
    if (stageFilter === "ALL") {
      return items;
    }
    return items.filter((item) => item.stage === stageFilter);
  }, [items, stageFilter]);

  const decisionIds = useMemo(() => {
    const ids = new Set<string>();
    for (const item of items) {
      if (typeof item.request_id === "string" && item.request_id.length > 0) {
        ids.add(item.request_id);
      }
    }
    return Array.from(ids).sort();
  }, [items]);

  const selectedDecisionEntry = useMemo(() => {
    if (!selectedDecisionId) {
      return null;
    }

    return items.find((item) => item.request_id === selectedDecisionId) ?? null;
  }, [items, selectedDecisionId]);

  const previousEntry = useMemo(() => {
    if (!selectedDecisionEntry) {
      return null;
    }

    const selectedIndex = items.findIndex((item) => item === selectedDecisionEntry);
    if (selectedIndex < 0 || selectedIndex >= items.length - 1) {
      return null;
    }
    return items[selectedIndex + 1] ?? null;
  }, [items, selectedDecisionEntry]);

  useEffect(() => {
    if (verificationStatus !== "running") {
      return undefined;
    }

    const timer = window.setInterval(() => {
      setAnimationStep((current) => {
        if (current >= 2) {
          return 2;
        }
        return current + 1;
      });
    }, 400);

    return () => {
      window.clearInterval(timer);
    };
  }, [verificationStatus]);

  const verifySelectedDecision = (): void => {
    setVerificationMessage(null);
    if (!selectedDecisionEntry) {
      setVerificationStatus("fail");
      setVerificationMessage(t("意思決定IDを選択してください。", "Please select a decision ID."));
      return;
    }

    if (!selectedDecisionEntry.sha256) {
      setVerificationStatus("fail");
      setVerificationMessage(t("選択ログに sha256 がありません。", "The selected log has no sha256."));
      return;
    }

    if (!previousEntry || !previousEntry.sha256) {
      setVerificationStatus("fail");
      setVerificationMessage(t("直前ログが見つからないため検証できません。", "Cannot verify without a previous log entry."));
      return;
    }

    setVerificationStatus("running");
    setAnimationStep(0);

    window.setTimeout(() => {
      const isTamperProof = selectedDecisionEntry.sha256_prev === previousEntry.sha256;
      setVerificationStatus(isTamperProof ? "pass" : "fail");
      setVerificationMessage(
        isTamperProof
          ? t("ハッシュチェーン整合: 改ざんは検出されませんでした。", "Hash chain verified: no tampering detected.")
          : t("ハッシュ不一致: 改ざんの可能性があります。", "Hash mismatch: potential tampering detected."),
      );
    }, 1400);
  };

  const createRegulatoryReport = (): RegulatoryReport | null => {
    setReportError(null);
    const startDate = reportStartDate.trim();
    const endDate = reportEndDate.trim();

    if (!startDate || !endDate) {
      setReportError(t("期間を指定してください。", "Please select both start and end dates."));
      return null;
    }

    if (startDate > endDate) {
      setReportError(t("開始日は終了日以前にしてください。", "Start date must be before end date."));
      return null;
    }

    const periodItems = items.filter((item) => isWithinPeriod(item, startDate, endDate));
    if (periodItems.length === 0) {
      setReportError(t("指定期間にデータがありません。", "No logs found for the selected period."));
      return null;
    }

    const stageMap = new Map<string, { count: number; passCount: number }>();
    for (const item of periodItems) {
      const stage = item.stage ?? "UNKNOWN";
      const current = stageMap.get(stage) ?? { count: 0, passCount: 0 };
      current.count += 1;
      if (isPassedEntry(item)) {
        current.passCount += 1;
      }
      stageMap.set(stage, current);
    }

    const fujiItems = periodItems.filter((item) => String(item.stage ?? "").toLowerCase().includes("fuji"));
    const fujiRejected = fujiItems.filter((item) => isRejectedEntry(item)).length;
    const sortedItems = [...periodItems].sort((a, b) => {
      const aTime = new Date(a.created_at ?? "").getTime();
      const bTime = new Date(b.created_at ?? "").getTime();
      return bTime - aTime;
    });

    let checkedLinks = 0;
    let mismatchLinks = 0;
    for (let index = 0; index < sortedItems.length - 1; index += 1) {
      const current = sortedItems[index];
      const previous = sortedItems[index + 1];
      if (!current?.sha256_prev || !previous?.sha256) {
        continue;
      }
      checkedLinks += 1;
      if (current.sha256_prev !== previous.sha256) {
        mismatchLinks += 1;
      }
    }

    const decisionIdsInPeriod = new Set(
      periodItems
        .map((item) => item.request_id)
        .filter((id): id is string => typeof id === "string" && id.length > 0),
    );

    const report: RegulatoryReport = {
      generatedAt: new Date().toISOString(),
      period: {
        startDate,
        endDate,
      },
      totalEntries: periodItems.length,
      totalDecisionIds: decisionIdsInPeriod.size,
      pipelineStageSummary: Array.from(stageMap.entries())
        .map(([stage, value]) => ({
          stage,
          count: value.count,
          passCount: value.passCount,
        }))
        .sort((a, b) => b.count - a.count),
      fujiGate: {
        totalEvaluations: fujiItems.length,
        rejected: fujiRejected,
        rejectionRate: fujiItems.length === 0 ? 0 : fujiRejected / fujiItems.length,
      },
      trustLogIntegrity: {
        checkedLinks,
        mismatchLinks,
        chainIntact: mismatchLinks === 0,
      },
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
    anchor.download = `regulatory-report-${report.period.startDate}-to-${report.period.endDate}.json`;
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

    const documentTitle = printWindow.document.createElement("title");
    documentTitle.textContent = "Regulatory Report";
    printWindow.document.head.appendChild(documentTitle);

    const container = printWindow.document.createElement("main");
    container.style.fontFamily = "Arial, sans-serif";
    container.style.padding = "20px";

    const title = printWindow.document.createElement("h1");
    title.textContent = "Regulatory Report Generator";
    container.appendChild(title);

    const generatedAt = printWindow.document.createElement("p");
    generatedAt.textContent = `Generated At: ${report.generatedAt}`;
    container.appendChild(generatedAt);

    const period = printWindow.document.createElement("p");
    period.textContent = `Period: ${report.period.startDate} to ${report.period.endDate}`;
    container.appendChild(period);

    const pipelineTitle = printWindow.document.createElement("h2");
    pipelineTitle.textContent = "Decision Pipeline Throughput";
    container.appendChild(pipelineTitle);

    const table = printWindow.document.createElement("table");
    table.setAttribute("border", "1");
    table.setAttribute("cellspacing", "0");
    table.setAttribute("cellpadding", "6");

    const tableHead = printWindow.document.createElement("thead");
    const headerRow = printWindow.document.createElement("tr");
    ["Stage", "Count", "Pass Count"].forEach((headerLabel) => {
      const cell = printWindow.document.createElement("th");
      cell.textContent = headerLabel;
      headerRow.appendChild(cell);
    });
    tableHead.appendChild(headerRow);

    const tableBody = printWindow.document.createElement("tbody");
    report.pipelineStageSummary.forEach((row) => {
      const tableRow = printWindow.document.createElement("tr");
      [row.stage, String(row.count), String(row.passCount)].forEach((value) => {
        const cell = printWindow.document.createElement("td");
        cell.textContent = value;
        tableRow.appendChild(cell);
      });
      tableBody.appendChild(tableRow);
    });

    table.appendChild(tableHead);
    table.appendChild(tableBody);
    container.appendChild(table);

    const fujiTitle = printWindow.document.createElement("h2");
    fujiTitle.textContent = "FUJI Gate Rejection Rate";
    container.appendChild(fujiTitle);

    const fujiParagraph = printWindow.document.createElement("p");
    fujiParagraph.textContent = `${report.fujiGate.rejected} / ${report.fujiGate.totalEvaluations} (${(report.fujiGate.rejectionRate * 100).toFixed(1)}%)`;
    container.appendChild(fujiParagraph);

    const integrityTitle = printWindow.document.createElement("h2");
    integrityTitle.textContent = "TrustLog Integrity Proof";
    container.appendChild(integrityTitle);

    const checkedLinks = printWindow.document.createElement("p");
    checkedLinks.textContent = `Checked Links: ${report.trustLogIntegrity.checkedLinks}`;
    container.appendChild(checkedLinks);

    const mismatches = printWindow.document.createElement("p");
    mismatches.textContent = `Mismatches: ${report.trustLogIntegrity.mismatchLinks}`;
    container.appendChild(mismatches);

    const chainIntact = printWindow.document.createElement("p");
    chainIntact.textContent = `Chain Intact: ${String(report.trustLogIntegrity.chainIntact)}`;
    container.appendChild(chainIntact);

    const securityNote = printWindow.document.createElement("p");
    securityNote.style.marginTop = "20px";
    securityNote.style.fontSize = "12px";
    securityNote.style.color = "#8a8a8a";
    securityNote.textContent = "Security note: Reports may contain sensitive audit metadata. Handle under your compliance policy.";
    container.appendChild(securityNote);

    printWindow.document.body.appendChild(container);
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

      const response = await fetchWithTimeout(`/api/veritas/v1/trust/logs?${params.toString()}`);

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
    setRequestResult(null);
    setError(null);
    if (!value) {
      setError(t("request_id を入力してください。", "Please enter request_id."));
      return;
    }

    setLoading(true);
    try {
      const response = await fetchWithTimeout(`/api/veritas/v1/trust/${encodeURIComponent(value)}`);

      if (!response.ok) {
        setError(`HTTP ${response.status}: ${t("request_id 検索に失敗しました。", "Failed to search request_id.")}`);
        return;
      }

      const payload: unknown = await response.json();
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
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <Card title="TrustLog Explorer" className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">
          {t(
            "/v1/trust/logs と /v1/trust/{request_id} を使って、監査証跡を時系列に確認します。",
            "Use /v1/trust/logs and /v1/trust/{request_id} to review audit evidence in chronological order.",
          )}
        </p>
      </Card>

      <Card title="Connection" className="bg-background/75">
        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm" disabled={loading} onClick={() => void loadLogs(null, true)}>
            {loading ? t("読み込み中...", "Loading...") : t("最新ログを読み込み", "Load latest logs")}
          </button>
          <button type="button" className="rounded-md border border-border px-3 py-2 text-sm" disabled={loading || !hasMore || !cursor} onClick={() => void loadLogs(cursor, false)}>
            {t("追加読み込み", "Load more")}
          </button>
        </div>
      </Card>

      <Card title={t("request_id 検索", "request_id Search")} className="bg-background/75">
        <div className="flex flex-col gap-2 md:flex-row">
          <input aria-label="request_id" className="w-full rounded-md border border-border bg-background px-2 py-2 text-sm" placeholder="request_id" value={requestId} onChange={(event) => setRequestId(event.target.value)} />
          <button type="button" className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm" disabled={loading} onClick={() => void searchByRequestId()}>
            {t("検索", "Search")}
          </button>
        </div>
        {requestResult ? <p className="mt-2 text-xs text-muted-foreground">count: {requestResult.count} / chain_ok: {String(requestResult.chain_ok)} / verification_result: {requestResult.verification_result}</p> : null}
      </Card>

      {error ? <p className="rounded-md border border-red-500/40 bg-red-500/10 p-2 text-sm text-red-300">{error}</p> : null}

      <Card title="Timeline" className="bg-background/75">
        <div className="mb-3 flex items-center gap-2 text-xs">
          <label htmlFor="stage-filter" className="font-medium">{t("ステージフィルタ", "Stage filter")}</label>
          <select id="stage-filter" className="rounded-md border border-border bg-background px-2 py-1" value={stageFilter} onChange={(event) => setStageFilter(event.target.value)}>
            {stageOptions.map((stage) => (<option key={stage} value={stage}>{stage}</option>))}
          </select>
          <span className="text-muted-foreground">{t("表示件数", "Visible")}: {filteredItems.length}</span>
        </div>

        <ol className="max-h-[520px] space-y-2 overflow-y-auto border-l border-border pl-4">
          {filteredItems.map((item, index) => {
            const id = `${item.request_id ?? "unknown"}-${index}`;
            const isSelected = selected === item;
            return (
              <li key={id}>
                <button
                  type="button"
                  className={`w-full rounded-md border px-3 py-2 text-left text-xs ${isSelected ? "border-primary/60 bg-primary/15" : "border-border bg-background/60"}`}
                  onClick={() => setSelected(item)}
                >
                  <p className="font-semibold">{item.stage ?? "UNKNOWN"}</p>
                  <p className="text-muted-foreground">{item.created_at ?? "no timestamp"}</p>
                  <p className="truncate text-muted-foreground">request_id: {item.request_id ?? "unknown"}</p>
                </button>
              </li>
            );
          })}
        </ol>
      </Card>

      <Card title="Selected JSON" className="bg-background/75">
        {selected ? (
          <details open>
            <summary className="cursor-pointer text-sm font-semibold">{t("JSON 展開", "Expand JSON")}</summary>
            <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs">{toPrettyJson(selected)}</pre>
          </details>
        ) : (
          <p className="text-sm text-muted-foreground">{t("ログを選択してください。", "Select a log.")}</p>
        )}
      </Card>

      <Card title={t("TrustLog インタラクティブ検証", "TrustLog Interactive Verification")} className="bg-background/75">
        <div className="space-y-3 text-sm">
          <div className="flex flex-col gap-2 md:flex-row md:items-end">
            <label className="flex-1 space-y-1 text-xs">
              <span className="font-medium">{t("意思決定ID", "Decision ID")}</span>
              <select
                className="w-full rounded-md border border-border bg-background px-2 py-2 text-sm"
                value={selectedDecisionId}
                onChange={(event) => setSelectedDecisionId(event.target.value)}
              >
                <option value="">{t("選択してください", "Select one")}</option>
                {decisionIds.map((id) => (
                  <option key={id} value={id}>{id}</option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm"
              disabled={loading || !selectedDecisionId}
              onClick={verifySelectedDecision}
            >
              {t("ハッシュチェーン検証", "Verify hash chain")}
            </button>
          </div>

          <div className="rounded-md border border-border bg-background/60 p-3">
            <p className="font-medium">{t("検証アニメーション", "Verification animation")}</p>
            <div className="mt-2 flex items-center gap-2 text-xs">
              <span className={`rounded border px-2 py-1 ${animationStep >= 1 ? "border-primary/60 bg-primary/15" : "border-border bg-background"}`}>
                {t("直前ログ", "Previous log")}: {shortHash(previousEntry?.sha256)}
              </span>
              <span aria-hidden="true" className={animationStep >= 2 ? "text-primary" : "text-muted-foreground"}>→</span>
              <span className={`rounded border px-2 py-1 ${animationStep >= 2 ? "border-primary/60 bg-primary/15" : "border-border bg-background"}`}>
                {t("sha256_prev", "sha256_prev")}: {shortHash(selectedDecisionEntry?.sha256_prev)}
              </span>
              <span aria-hidden="true" className={animationStep >= 2 ? "text-primary" : "text-muted-foreground"}>→</span>
              <span className="rounded border border-border bg-background px-2 py-1">
                {t("現在ログ", "Current log")}: {shortHash(selectedDecisionEntry?.sha256)}
              </span>
            </div>
          </div>

          {verificationStatus === "pass" ? (
            <p className="inline-flex w-fit rounded-full border border-emerald-500/60 bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">
              TAMPER-PROOF ✅
            </p>
          ) : null}

          {verificationMessage ? (
            <p className={`rounded-md border p-2 text-xs ${verificationStatus === "pass" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300" : "border-amber-500/40 bg-amber-500/10 text-amber-200"}`}>
              {verificationMessage}
            </p>
          ) : null}
        </div>
      </Card>

      <Card title={t("第三者監査用エクスポート", "Regulatory Report Generator")} className="bg-background/75">
        <div className="space-y-3 text-sm">
          <p className="text-xs text-muted-foreground">
            {t(
              "指定期間の決定パイプライン通過データ、FUJI Gate拒絶率、TrustLog整合性証明をPDF/JSONで出力します。",
              "Generate PDF/JSON with pipeline throughput, FUJI gate rejection rate, and TrustLog integrity proof for a selected period.",
            )}
          </p>

          <div className="grid gap-2 md:grid-cols-2">
            <label className="space-y-1 text-xs">
              <span className="font-medium">{t("開始日", "Start date")}</span>
              <input
                type="date"
                className="w-full rounded-md border border-border bg-background px-2 py-2"
                value={reportStartDate}
                onChange={(event) => setReportStartDate(event.target.value)}
              />
            </label>
            <label className="space-y-1 text-xs">
              <span className="font-medium">{t("終了日", "End date")}</span>
              <input
                type="date"
                className="w-full rounded-md border border-border bg-background px-2 py-2"
                value={reportEndDate}
                onChange={(event) => setReportEndDate(event.target.value)}
              />
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <button type="button" className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm" onClick={downloadJsonReport}>
              {t("JSON生成", "Generate JSON")}
            </button>
            <button type="button" className="rounded-md border border-primary/60 bg-primary/20 px-3 py-2 text-sm" onClick={generatePdfReport}>
              {t("PDF生成", "Generate PDF")}
            </button>
          </div>

          {reportError ? <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">{reportError}</p> : null}

          {latestReport ? (
            <div className="rounded-md border border-border bg-background/60 p-3 text-xs">
              <p>entries: {latestReport.totalEntries} / decision_ids: {latestReport.totalDecisionIds}</p>
              <p>
                FUJI rejection: {latestReport.fujiGate.rejected}/{latestReport.fujiGate.totalEvaluations}
                {` (${(latestReport.fujiGate.rejectionRate * 100).toFixed(1)}%)`}
              </p>
              <p>
                chain links: {latestReport.trustLogIntegrity.checkedLinks} / mismatches: {latestReport.trustLogIntegrity.mismatchLinks}
              </p>
            </div>
          ) : null}

          <p className="rounded-md border border-amber-500/30 bg-amber-500/10 p-2 text-xs text-amber-100">
            {t(
              "セキュリティ警告: 出力レポートに監査メタデータが含まれる可能性があります。共有前にPII・機密情報の取り扱いポリシーを確認してください。",
              "Security warning: Exported reports may include sensitive audit metadata. Confirm your PII and confidential-data handling policy before sharing.",
            )}
          </p>
        </div>
      </Card>
    </div>
  );
}
