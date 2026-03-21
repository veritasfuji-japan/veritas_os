"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import type { ExportFormat, RedactionMode, RegulatoryReport } from "../audit-types";
import { computeAuditSummary } from "../audit-types";
import type { TrustLogItem } from "../../../lib/api-validators";

interface ExportPanelProps {
  sortedItems: TrustLogItem[];
  reportStartDate: string;
  reportEndDate: string;
  redactionMode: RedactionMode;
  exportFormat: ExportFormat;
  confirmPiiRisk: boolean;
  reportError: string | null;
  latestReport: RegulatoryReport | null;
  exportTargetCount: number;
  onReportStartDateChange: (v: string) => void;
  onReportEndDateChange: (v: string) => void;
  onRedactionModeChange: (v: RedactionMode) => void;
  onExportFormatChange: (v: ExportFormat) => void;
  onConfirmPiiRiskChange: (v: boolean) => void;
  onReportError: (v: string | null) => void;
  onLatestReport: (v: RegulatoryReport | null) => void;
}

export function ExportPanel({
  sortedItems,
  reportStartDate,
  reportEndDate,
  redactionMode,
  exportFormat,
  confirmPiiRisk,
  reportError,
  latestReport,
  exportTargetCount,
  onReportStartDateChange,
  onReportEndDateChange,
  onRedactionModeChange,
  onExportFormatChange,
  onConfirmPiiRiskChange,
  onReportError,
  onLatestReport,
}: ExportPanelProps): JSX.Element {
  const { t } = useI18n();

  const createRegulatoryReport = (): RegulatoryReport | null => {
    onReportError(null);
    if (!confirmPiiRisk) {
      onReportError(t("PII/metadata warning を確認してください。", "Please acknowledge the PII/metadata warning."));
      return null;
    }
    if (!reportStartDate || !reportEndDate) {
      onReportError(t("期間を指定してください。", "Please select both start and end dates."));
      return null;
    }
    const start = new Date(`${reportStartDate}T00:00:00.000Z`).getTime();
    const end = new Date(`${reportEndDate}T23:59:59.999Z`).getTime();
    const periodItems = sortedItems.filter((item) => {
      const stamp = new Date(item.created_at ?? "").getTime();
      return Number.isFinite(stamp) && stamp >= start && stamp <= end;
    });
    if (periodItems.length === 0) {
      onReportError(t("指定期間にデータがありません。", "No logs found for the selected period."));
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
    onLatestReport(report);
    return report;
  };

  const downloadJsonReport = (): void => {
    const report = createRegulatoryReport();
    if (!report) return;
    const reportBlob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
    const objectUrl = URL.createObjectURL(reportBlob);
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = `audit-report-${reportStartDate}-${reportEndDate}.json`;
    anchor.click();
    URL.revokeObjectURL(objectUrl);
  };

  const generatePdfReport = (): void => {
    const report = createRegulatoryReport();
    if (!report) return;
    const printWindow = window.open("", "_blank", "noopener,noreferrer,width=900,height=700");
    if (!printWindow) {
      onReportError(t("PDFウィンドウを開けませんでした。", "Failed to open PDF print window."));
      return;
    }
    const doc = printWindow.document;
    const title = doc.createElement("h1");
    title.textContent = "Regulatory Report Generator";
    const warning = doc.createElement("p");
    warning.textContent = "Security note: Report may include PII and sensitive metadata.";
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

  const REDACTION_OPTIONS = [
    { value: "full" as const, label: t("完全出力", "Full"), desc: t("すべてのフィールドを含む", "Includes all fields") },
    { value: "redacted" as const, label: t("墨消し", "Redacted"), desc: t("PII関連フィールドを除外", "PII fields removed") },
    { value: "metadata-only" as const, label: t("メタデータのみ", "Metadata only"), desc: t("監査メタデータのみ", "Audit metadata only") },
  ] as const;

  return (
    <Card
      title={t("第三者監査用エクスポート", "Regulatory Report Generator")}
      titleSize="md"
      variant="elevated"
      accent="warning"
    >
      <div className="space-y-4 text-sm">
        {/* Period selection */}
        <div>
          <p className="mb-1 text-xs font-semibold">{t("対象期間", "Export Period")}</p>
          <div className="grid gap-3 md:grid-cols-2">
            <input
              aria-label={t("監査レポート開始日", "Audit report start date")}
              type="date"
              value={reportStartDate}
              onChange={(e) => onReportStartDateChange(e.target.value)}
              className="rounded border border-border px-3 py-2"
            />
            <input
              aria-label={t("監査レポート終了日", "Audit report end date")}
              type="date"
              value={reportEndDate}
              onChange={(e) => onReportEndDateChange(e.target.value)}
              className="rounded border border-border px-3 py-2"
            />
          </div>
          {reportStartDate && reportEndDate && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("エクスポート対象", "Export target")}: {exportTargetCount} {t("件", "entries")}
            </p>
          )}
        </div>

        {/* Redaction mode */}
        <fieldset className="space-y-1">
          <legend className="text-xs font-semibold">{t("墨消しモード", "Redaction Mode")}</legend>
          <div className="flex gap-3 text-xs">
            {REDACTION_OPTIONS.map((opt) => (
              <label key={opt.value} className="flex items-start gap-1.5">
                <input
                  aria-label={opt.label}
                  type="radio"
                  name="redaction"
                  value={opt.value}
                  checked={redactionMode === opt.value}
                  onChange={() => onRedactionModeChange(opt.value)}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium">{opt.label}</span>
                  <br />
                  <span className="text-xs text-muted-foreground">{opt.desc}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {/* Format selection */}
        <fieldset className="space-y-1">
          <legend className="text-xs font-semibold">{t("出力形式", "Export Format")}</legend>
          <div className="flex gap-4 text-xs">
            <label className="flex items-start gap-1.5">
              <input aria-label="JSON" type="radio" name="exportFormat" value="json" checked={exportFormat === "json"} onChange={() => onExportFormatChange("json")} className="mt-0.5" />
              <span>
                <span className="font-medium">JSON</span><br />
                <span className="text-xs text-muted-foreground">{t("機械可読形式。APIやスクリプトでの処理に最適", "Machine-readable. Best for API and script processing")}</span>
              </span>
            </label>
            <label className="flex items-start gap-1.5">
              <input aria-label="PDF" type="radio" name="exportFormat" value="pdf" checked={exportFormat === "pdf"} onChange={() => onExportFormatChange("pdf")} className="mt-0.5" />
              <span>
                <span className="font-medium">PDF</span><br />
                <span className="text-xs text-muted-foreground">{t("印刷用。第三者監査提出に適した形式", "Printable. Suitable for third-party audit submission")}</span>
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
              checked={confirmPiiRisk}
              onChange={(e) => onConfirmPiiRiskChange(e.target.checked)}
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
        <button type="button" className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2 text-sm" onClick={handleExport}>
          {exportFormat === "json" ? t("JSON生成", "Generate JSON") : t("PDF生成", "Generate PDF")}
        </button>

        {reportError ? <p className="text-xs text-warning">{reportError}</p> : null}
        {latestReport ? (
          <div className="rounded border border-border p-2 text-xs">
            <p>
              entries: {latestReport.totalEntries} / verified: {latestReport.verified} / broken: {latestReport.broken} /
              missing: {latestReport.missing} / orphan: {latestReport.orphan} / mismatches: {latestReport.mismatchLinks}
            </p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}
