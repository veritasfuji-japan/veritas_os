"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../../components/i18n-provider";
import { StatCard } from "../../../components/ui";
import { STATUS_BG } from "../constants";

interface AuditSummaryData {
  total: number;
  verified: number;
  broken: number;
  missing: number;
  orphan: number;
  replayLinked: number;
  policyVersions: Record<string, number>;
}

interface AuditSummaryPanelProps {
  summary: AuditSummaryData;
  hasItems: boolean;
}

export function AuditSummaryPanel({ summary, hasItems }: AuditSummaryPanelProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card title="Audit Summary" titleSize="sm" variant="elevated">
      {!hasItems ? (
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
            <StatCard label={t("全エントリ", "Total")} value={summary.total} />
            <StatCard label="Verified" value={summary.verified} variant="success" className={STATUS_BG.verified} />
            <StatCard label="Broken" value={summary.broken} variant="danger" className={STATUS_BG.broken} />
            <StatCard label="Missing" value={summary.missing} variant="warning" className={STATUS_BG.missing} />
            <StatCard label="Orphan" value={summary.orphan} variant="info" className={STATUS_BG.orphan} />
            <StatCard label={t("リプレイ連携", "Replay Linked")} value={summary.replayLinked} />
          </div>

          {/* Policy version distribution */}
          {Object.keys(summary.policyVersions).length > 0 && (
            <div>
              <p className="mb-1 text-xs font-semibold">
                {t("ポリシーバージョン分布", "Policy Version Distribution")}
              </p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(summary.policyVersions).map(([version, count]) => (
                  <span key={version} className="rounded border border-border px-2 py-0.5 font-mono text-2xs">
                    {version}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Integrity bar */}
          {summary.total > 0 && (
            <div>
              <div className="flex h-2 overflow-hidden rounded-full">
                {summary.verified > 0 && (
                  <div className="bg-success" style={{ width: `${(summary.verified / summary.total) * 100}%` }} />
                )}
                {summary.broken > 0 && (
                  <div className="bg-danger" style={{ width: `${(summary.broken / summary.total) * 100}%` }} />
                )}
                {summary.missing > 0 && (
                  <div className="bg-warning" style={{ width: `${(summary.missing / summary.total) * 100}%` }} />
                )}
                {summary.orphan > 0 && (
                  <div className="bg-info" style={{ width: `${(summary.orphan / summary.total) * 100}%` }} />
                )}
              </div>
              <p className="mt-1 text-2xs text-muted-foreground">
                {t("チェーン整合率", "Chain integrity")}:{" "}
                {Math.round((summary.verified / summary.total) * 100)}%
              </p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
