"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { ErrorBanner } from "../../components/ui";
import { classifyChain } from "./audit-types";
import { useAuditData } from "./hooks/useAuditData";
import { SearchPanel } from "./components/SearchPanel";
import { DetailPanel } from "./components/DetailPanel";
import { AuditSummaryPanel } from "./components/AuditSummaryPanel";
import { AuditTimeline } from "./components/AuditTimeline";
import { VerificationPanel } from "./components/VerificationPanel";
import { ExportPanel } from "./components/ExportPanel";

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function TrustLogExplorerPage(): JSX.Element {
  const { t } = useI18n();
  const data = useAuditData();

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
      {/* Page header */}
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

      {/* Search */}
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

      {data.bindReceiptIdFromQuery ? (
        <Card
          title="Bind Receipt Trace"
          description={t(
            "Governance から指定された bind receipt を追跡中です。",
            "Tracing bind receipt specified from Governance.",
          )}
          variant="elevated"
        >
          <div className="space-y-2 text-xs">
            <p>
              bind_receipt_id: <span className="font-mono">{data.bindReceiptIdFromQuery}</span>
            </p>
            {data.bindReceiptLookupLoading ? (
              <p className="text-muted-foreground">
                {t("bind receipt を取得しています...", "Fetching bind receipt...")}
              </p>
            ) : null}
            {!data.bindReceiptLookupLoading && !data.bindReceiptLookupError ? (
              <p className={data.bindReceiptFoundInTimeline ? "text-success" : "text-warning"}>
                {data.bindReceiptFoundInTimeline
                  ? t(
                      "関連する監査ログをタイムラインで選択しました。",
                      "Matched audit log has been focused in the timeline.",
                    )
                  : t(
                      "bind receipt は取得済みですが、現在読み込まれているタイムラインには未表示です。",
                      "Bind receipt was retrieved, but no matching timeline item is currently loaded.",
                    )}
              </p>
            ) : null}
          </div>
        </Card>
      ) : null}

      {data.error ? (
        <ErrorBanner
          message={data.error}
          onRetry={() => void data.loadLogs(null, true)}
          retryLabel={t("再試行", "Retry")}
        />
      ) : null}

      {data.bindReceiptLookupError ? (
        <ErrorBanner message={data.bindReceiptLookupError} />
      ) : null}

      {/* Summary */}
      <AuditSummaryPanel
        summary={data.auditSummary}
        hasItems={data.filteredItems.length > 0}
      />

      {/* Timeline */}
      <AuditTimeline
        filteredItems={data.filteredItems}
        stageFilter={data.stageFilter}
        stageOptions={data.stageOptions}
        selected={data.selected}
        onStageFilterChange={data.setStageFilter}
        onSelect={data.setSelected}
        onDetailTabChange={data.setDetailTab}
      />

      {/* Detail */}
      <DetailPanel
        selected={data.selected}
        selectedChain={data.selectedChain}
        previousEntry={data.previousEntry}
        nextEntry={data.nextEntry}
        detailTab={data.detailTab}
        onDetailTabChange={data.setDetailTab}
      />

      {/* Verification */}
      <VerificationPanel
        decisionIds={data.decisionIds}
        selectedDecisionId={data.selectedDecisionId}
        selectedDecisionEntry={data.selectedDecisionEntry}
        verificationMessage={data.verificationMessage}
        onSelectedDecisionIdChange={data.setSelectedDecisionId}
        onVerify={verifySelectedDecision}
      />

      {/* Export */}
      <ExportPanel
        sortedItems={data.sortedItems}
        reportStartDate={data.reportStartDate}
        reportEndDate={data.reportEndDate}
        redactionMode={data.redactionMode}
        exportFormat={data.exportFormat}
        confirmPiiRisk={data.confirmPiiRisk}
        reportError={data.reportError}
        latestReport={data.latestReport}
        exportTargetCount={data.exportTargetCount}
        onReportStartDateChange={data.setReportStartDate}
        onReportEndDateChange={data.setReportEndDate}
        onRedactionModeChange={data.setRedactionMode}
        onExportFormatChange={data.setExportFormat}
        onConfirmPiiRiskChange={data.setConfirmPiiRisk}
        onReportError={data.setReportError}
        onLatestReport={data.setLatestReport}
      />
    </div>
  );
}
