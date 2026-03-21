"use client";

import Link from "next/link";
import { useI18n } from "../../../components/i18n-provider";
import type { FlaggedEntry } from "../risk-types";
import { SEVERITY_CLASSES, STATUS_LABELS } from "../constants";

interface DrilldownPanelProps {
  entry: FlaggedEntry | null;
}

export function DrilldownPanel({ entry }: DrilldownPanelProps): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs" data-testid="drilldown-panel">
      <p className="font-semibold">Drilldown panel</p>
      {entry ? (
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          <div className="space-y-2">
            <div>
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Request ID / Seed</p>
              <p className="font-mono text-[11px]">{entry.point.id}</p>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground">Uncertainty</p>
                <p className="font-mono font-semibold">{entry.point.uncertainty.toFixed(3)}</p>
              </div>
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground">Risk score</p>
                <p className="font-mono font-semibold">{entry.point.risk.toFixed(3)}</p>
              </div>
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Severity / Status</p>
              <div className="mt-0.5 flex items-center gap-2">
                <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${SEVERITY_CLASSES[entry.severity]}`}>
                  {entry.severity}
                </span>
                <span className="rounded bg-muted/40 px-1 py-0.5 text-[9px]">{STATUS_LABELS[entry.status]}</span>
              </div>
            </div>
          </div>
          <div className="space-y-2">
            <div>
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Related policy hits</p>
              {entry.relatedPolicyHits.length > 0 ? (
                <ul className="mt-0.5 space-y-0.5">
                  {entry.relatedPolicyHits.map((hit) => (
                    <li key={hit} className="rounded bg-warning/10 px-1.5 py-0.5 text-[10px]">⚡ {hit}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">No policy hits</p>
              )}
            </div>
            <div>
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Stage anomalies</p>
              {entry.stageAnomalies.length > 0 ? (
                <ul className="mt-0.5 space-y-0.5">
                  {entry.stageAnomalies.map((anomaly) => (
                    <li key={anomaly} className="rounded bg-danger/10 px-1.5 py-0.5 text-[10px]">⚠ {anomaly}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">No anomalies detected</p>
              )}
            </div>
          </div>
          <div className="md:col-span-2 flex flex-wrap gap-1 border-t border-border/30 pt-2">
            <Link href={`/console?request_id=${encodeURIComponent(entry.point.id)}`} className="rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40 inline-flex items-center gap-1">
              <span aria-hidden>⚡</span> Open in Decision
            </Link>
            <Link href={`/audit?request_id=${encodeURIComponent(entry.point.id)}`} className="rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40 inline-flex items-center gap-1">
              <span aria-hidden>📋</span> Open in TrustLog
            </Link>
            <Link href="/governance" className="rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40 inline-flex items-center gap-1">
              <span aria-hidden>🛡</span> Adjust in Governance
            </Link>
          </div>
        </div>
      ) : (
        <div className="mt-2 rounded-lg border border-border/30 bg-muted/10 px-3 py-4 text-center text-muted-foreground" data-testid="empty-drilldown">
          <p className="text-sm font-medium">{t("監視対象", "Monitoring target")}</p>
          <p className="mt-1 text-[11px]">{t("ポイントを選択するとドリルダウン情報が表示されます。リアルタイムでリスク監視を継続中です。", "Select a point to view drilldown details. Real-time risk monitoring continues.")}</p>
        </div>
      )}
    </div>
  );
}
