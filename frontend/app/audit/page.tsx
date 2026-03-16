"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import {
  classifyChain,
  computeAuditSummary,
  getString,
  type SearchField,
} from "./audit-types";
import { STATUS_BG, STATUS_COLORS, STATUS_DOT } from "./constants";
import { useAuditData } from "./hooks/useAuditData";
import { SearchPanel } from "./components/SearchPanel";
import { DetailPanel } from "./components/DetailPanel";
import type { ExportFormat, RedactionMode, RegulatoryReport } from "./audit-types";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function TrustLogExplorerPage(): JSX.Element {
  const { t } = useI18n();
  const data = useAuditData();

  /* -- export actions (kept inline since they use multiple state setters) -- */

  const createRegulatoryReport = (): RegulatoryReport | null => {
    data.setReportError(null);
    if (!data.confirmPiiRisk) {
      data.setReportError(
        t(
          "PII/metadata warning を確認してください。",
          "Please acknowledge the PII/metadata warning.",
        ),
      );
      return null;
    }
    if (!data.reportStartDate || !data.reportEndDate) {
      data.setReportError(
        t("期間を指定してください。", "Please select both start and end dates."),
      );
      return null;
    }
    const start = new Date(`${data.reportStartDate}T00:00:00.000Z`).getTime();
    const end = new Date(`${data.reportEndDate}T23:59:59.999Z`).getTime();
    const periodItems = data.sortedItems.filter((item) => {
      const stamp = new Date(item.created_at ?? "").getTime();
      return Number.isFinite(stamp) && stamp >= start && stamp <= end;
    });
    if (periodItems.length === 0) {
      data.setReportError(
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
      redactionMode: data.redactionMode,
      policyVersions: summary.policyVersions,
    };
    data.setLatestReport(report);
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
    anchor.download = `audit-report-${data.reportStartDate}-${data.reportEndDate}.json`;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  };

  const generatePdfReport = (): void => {
    const report = createRegulatoryReport();
    if (!report) return;
    const printWindow = window.open(
      "",
      "_blank",
      "noopener,noreferrer,width=900,height=700",
    );
    if (!printWindow) {
      data.setReportError(
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
    if (data.exportFormat === "pdf") {
      generatePdfReport();
    } else {
      downloadJsonReport();
    }
  };

  const verifySelectedDecision = (): void => {
    if (!data.selectedDecisionEntry) {
      data.setVerificationMessage(
        t("意思決定IDを選択してください。", "Please select a decision ID."),
      );
      return;
    }
    const idx = data.sortedItems.findIndex((item) => item === data.selectedDecisionEntry);
    const previous = idx >= 0 ? data.sortedItems[idx + 1] ?? null : null;
    const result = classifyChain(data.selectedDecisionEntry, previous);
    if (result.status === "verified") {
      data.setVerificationMessage("TAMPER-PROOF \u2705");
      return;
    }
    data.setVerificationMessage(`${result.status.toUpperCase()}: ${result.reason}`);
  };

  /* ---------------------------------------------------------------- */
  /*  Render                                                           */
  /* ---------------------------------------------------------------- */

  return (
    <div className="space-y-6">
      {/* Empty-state hero / page purpose */}
      <Card
        title="TrustLog Explorer"
        description={t(
          "ハッシュチェーン監査証跡の人間検証・エクスポート",
          "Hash-chained audit trail for human verification and export",
        )}
        variant="glass"
        accent="info"
        className="border-info/15"
      >
        <div className="space-y-1 text-xs text-muted-foreground">
          <p>
            {t(
              "この画面では、AI意思決定のハッシュチェーン整合性の検証、タイムライン上での監査対象の特定、decision / replay / metadata の追跡、安全なエクスポートを行えます。",
              "Use this page to verify hash-chain integrity of AI decisions, identify audit targets on the timeline, trace decision / replay / metadata links, and export evidence safely.",
            )}
          </p>
          {data.items.length === 0 && (
            <p className="mt-2 rounded border border-info/20 bg-info/5 px-3 py-2">
              {t(
                "まず「最新ログを読み込み」で監査ログを取得してください。読み込み後、タイムラインにエントリが表示され、ハッシュチェーン検証・横断検索・エクスポートが可能になります。",
                "Start by clicking \"Load latest logs\" to fetch audit entries. Once loaded, the timeline will populate and you can verify hash chains, cross-search, and export evidence.",
              )}
            </p>
          )}
        </div>
      </Card>

      {/* Search: Connection + request_id + cross-search */}
      <SearchPanel
        requestId={data.requestId}
        onRequestIdChange={data.setRequestId}
        requestResult={data.requestResult}
        onSearchByRequestId={() => void data.searchByRequestId()}
        crossSearch={data.crossSearch}
        onCrossSearchChange={data.setCrossSearch}
        filteredCount={data.filteredItems.length}
        loading={data.loading}
        hasMore={data.hasMore}
        cursor={data.cursor}
        onLoadLogs={(c, r) => void data.loadLogs(c, r)}
      />

      {data.error ? (
        <p className="rounded-lg border border-danger/30 bg-danger/10 px-3 py-2 text-sm text-danger">
          {data.error}
        </p>
      ) : null}

      {/* Enhanced Audit Summary */}
      <Card title="Audit Summary" titleSize="sm" variant="elevated">
        {data.filteredItems.length === 0 ? (
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
                <p className="text-lg font-semibold">{data.auditSummary.total}</p>
                <p className="text-2xs text-muted-foreground">
                  {t("全エントリ", "Total")}
                </p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.verified}`}
              >
                <p className="text-lg font-semibold text-success">
                  {data.auditSummary.verified}
                </p>
                <p className="text-2xs text-muted-foreground">Verified</p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.broken}`}
              >
                <p className="text-lg font-semibold text-danger">
                  {data.auditSummary.broken}
                </p>
                <p className="text-2xs text-muted-foreground">Broken</p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.missing}`}
              >
                <p className="text-lg font-semibold text-warning">
                  {data.auditSummary.missing}
                </p>
                <p className="text-2xs text-muted-foreground">Missing</p>
              </div>
              <div
                className={`rounded border px-3 py-2 text-center ${STATUS_BG.orphan}`}
              >
                <p className="text-lg font-semibold text-info">
                  {data.auditSummary.orphan}
                </p>
                <p className="text-2xs text-muted-foreground">Orphan</p>
              </div>
              <div className="rounded border border-border px-3 py-2 text-center">
                <p className="text-lg font-semibold">
                  {data.auditSummary.replayLinked}
                </p>
                <p className="text-2xs text-muted-foreground">
                  {t("リプレイ連携", "Replay Linked")}
                </p>
              </div>
            </div>

            {/* Policy version distribution */}
            {Object.keys(data.auditSummary.policyVersions).length > 0 && (
              <div>
                <p className="mb-1 text-xs font-semibold">
                  {t("ポリシーバージョン分布", "Policy Version Distribution")}
                </p>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(data.auditSummary.policyVersions).map(
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
            {data.auditSummary.total > 0 && (
              <div>
                <div className="flex h-2 overflow-hidden rounded-full">
                  {data.auditSummary.verified > 0 && (
                    <div
                      className="bg-success"
                      style={{
                        width: `${(data.auditSummary.verified / data.auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                  {data.auditSummary.broken > 0 && (
                    <div
                      className="bg-danger"
                      style={{
                        width: `${(data.auditSummary.broken / data.auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                  {data.auditSummary.missing > 0 && (
                    <div
                      className="bg-warning"
                      style={{
                        width: `${(data.auditSummary.missing / data.auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                  {data.auditSummary.orphan > 0 && (
                    <div
                      className="bg-info"
                      style={{
                        width: `${(data.auditSummary.orphan / data.auditSummary.total) * 100}%`,
                      }}
                    />
                  )}
                </div>
                <p className="mt-1 text-2xs text-muted-foreground">
                  {t("チェーン整合率", "Chain integrity")}:{" "}
                  {Math.round(
                    (data.auditSummary.verified / data.auditSummary.total) * 100,
                  )}
                  %
                </p>
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Enhanced Timeline */}
      <Card title="Timeline" titleSize="md" variant="elevated">
        <div className="mb-2 flex items-center gap-2">
          <label htmlFor="stage-filter" className="text-xs">
            Stage
          </label>
          <select
            id="stage-filter"
            value={data.stageFilter}
            onChange={(e) => data.setStageFilter(e.target.value)}
            className="rounded border border-border px-2 py-1 text-xs"
          >
            {data.stageOptions.map((stage) => (
              <option key={stage} value={stage}>
                {stage}
              </option>
            ))}
          </select>
          <span className="ml-auto text-xs">
            {t("表示件数", "Visible")}: {data.filteredItems.length}
          </span>
        </div>
        {data.filteredItems.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t(
              "監査対象が未読込です。request_id/decision_id・ハッシュ整合・リプレイ関連をここで確認できます。",
              "No logs loaded yet. This timeline verifies request/decision IDs, hash chain, and replay linkage.",
            )}
          </p>
        ) : null}

        {/* Column header */}
        {data.filteredItems.length > 0 && (
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
          {data.filteredItems.map((item, index) => {
            const chain = classifyChain(
              item,
              data.filteredItems[index + 1] ?? null,
            );
            const isSelected = data.selected === item;
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
                    data.setSelected(item);
                    data.setDetailTab("summary");
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
                    <span>{getString(item, "stage")}</span>
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

      {/* Selected Audit detail with tabs */}
      <DetailPanel
        selected={data.selected}
        selectedChain={data.selectedChain}
        previousEntry={data.previousEntry}
        nextEntry={data.nextEntry}
        detailTab={data.detailTab}
        onDetailTabChange={data.setDetailTab}
      />

      {/* Hash Chain Verification */}
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
              value={data.selectedDecisionId}
              onChange={(e) => data.setSelectedDecisionId(e.target.value)}
            >
              <option value="">
                {t("意思決定IDを選択", "Select a decision ID")}
              </option>
              {data.decisionIds.map((id) => (
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
          {data.verificationMessage ? (
            <p className="text-xs">{data.verificationMessage}</p>
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

      {/* Export */}
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
                value={data.reportStartDate}
                onChange={(e) => data.setReportStartDate(e.target.value)}
                className="rounded border border-border px-3 py-2"
              />
              <input
                aria-label={t("監査レポート終了日", "Audit report end date")}
                type="date"
                value={data.reportEndDate}
                onChange={(e) => data.setReportEndDate(e.target.value)}
                className="rounded border border-border px-3 py-2"
              />
            </div>
            {data.reportStartDate && data.reportEndDate && (
              <p className="mt-1 text-xs text-muted-foreground">
                {t("エクスポート対象", "Export target")}: {data.exportTargetCount}{" "}
                {t("件", "entries")}
              </p>
            )}
          </div>

          {/* Redaction mode */}
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold">
              {t("墨消しモード", "Redaction Mode")}
            </legend>
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
                    aria-label={opt.label}
                    type="radio"
                    name="redaction"
                    value={opt.value}
                    checked={data.redactionMode === opt.value}
                    onChange={() => data.setRedactionMode(opt.value)}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium">{opt.label}</span>
                    <br />
                    <span className="text-xs text-muted-foreground">
                      {opt.desc}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {/* Format selection */}
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold">
              {t("出力形式", "Export Format")}
            </legend>
            <div className="flex gap-4 text-xs">
              <label className="flex items-start gap-1.5">
                <input
                  aria-label="JSON"
                  type="radio"
                  name="exportFormat"
                  value="json"
                  checked={data.exportFormat === "json"}
                  onChange={() => data.setExportFormat("json")}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">JSON</span>
                  <br />
                  <span className="text-xs text-muted-foreground">
                    {t(
                      "機械可読形式。APIやスクリプトでの処理に最適",
                      "Machine-readable. Best for API and script processing",
                    )}
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-1.5">
                <input
                  aria-label="PDF"
                  type="radio"
                  name="exportFormat"
                  value="pdf"
                  checked={data.exportFormat === "pdf"}
                  onChange={() => data.setExportFormat("pdf")}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">PDF</span>
                  <br />
                  <span className="text-xs text-muted-foreground">
                    {t(
                      "印刷用。第三者監査提出に適した形式",
                      "Printable. Suitable for third-party audit submission",
                    )}
                  </span>
                </span>
              </label>
            </div>
          </fieldset>

          {/* PII acknowledgement */}
          <div className="rounded border border-warning/30 bg-warning/5 p-3">
            <label className="flex items-start gap-2 text-xs">
              <input
                aria-label={t("PII/metadata warningの確認", "Acknowledge PII/metadata warning")}
                type="checkbox"
                checked={data.confirmPiiRisk}
                onChange={(e) => data.setConfirmPiiRisk(e.target.checked)}
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
            {data.exportFormat === "json"
              ? t("JSON生成", "Generate JSON")
              : t("PDF生成", "Generate PDF")}
          </button>

          {data.reportError ? (
            <p className="text-xs text-warning">{data.reportError}</p>
          ) : null}
          {data.latestReport ? (
            <div className="rounded border border-border p-2 text-xs">
              <p>
                entries: {data.latestReport.totalEntries} / verified:{" "}
                {data.latestReport.verified} / broken: {data.latestReport.broken} /
                missing: {data.latestReport.missing} / orphan:{" "}
                {data.latestReport.orphan} / mismatches: {data.latestReport.mismatchLinks}
              </p>
            </div>
          ) : null}
        </div>
      </Card>
    </div>
  );
}
