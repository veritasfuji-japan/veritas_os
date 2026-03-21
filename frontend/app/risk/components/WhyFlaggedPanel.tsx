"use client";

import { useI18n } from "../../../components/i18n-provider";
import type { FlaggedEntry } from "../risk-types";

interface WhyFlaggedPanelProps {
  entry: FlaggedEntry | null;
}

export function WhyFlaggedPanel({ entry }: WhyFlaggedPanelProps): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs" data-testid="why-flagged">
      <p className="font-semibold">Why flagged</p>
      {entry ? (
        <div className="mt-2 space-y-3">
          <p className="font-mono text-[10px] text-muted-foreground">{entry.point.id}</p>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg border border-border/40 px-2 py-1.5">
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Policy confidence</p>
              <p className={`font-mono font-semibold ${entry.reason.policyConfidence < 0.3 ? "text-danger" : entry.reason.policyConfidence < 0.6 ? "text-warning" : "text-success"}`}>
                {(entry.reason.policyConfidence * 100).toFixed(0)}%
              </p>
            </div>
            <div className="rounded-lg border border-border/40 px-2 py-1.5">
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Unstable output</p>
              <p className={`font-semibold ${entry.reason.unstableOutputSignal ? "text-danger" : "text-success"}`}>
                {entry.reason.unstableOutputSignal ? "Detected" : "Stable"}
              </p>
            </div>
            <div className="rounded-lg border border-border/40 px-2 py-1.5">
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Retrieval anomaly</p>
              <p className={`font-semibold ${entry.reason.retrievalAnomaly ? "text-warning" : "text-success"}`}>
                {entry.reason.retrievalAnomaly ? "Anomaly" : "Normal"}
              </p>
            </div>
            <div className="rounded-lg border border-border/40 px-2 py-1.5">
              <p className="text-[10px] font-semibold uppercase text-muted-foreground">Cluster</p>
              <p className="font-semibold">{entry.cluster}</p>
            </div>
          </div>
          <div className="rounded-lg border border-border/40 bg-muted/5 px-2 py-1.5">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground">Analysis</p>
            <p className="mt-0.5 text-muted-foreground">{entry.reason.summary}</p>
          </div>
          <div className="rounded-lg border border-primary/30 bg-primary/5 px-2 py-1.5">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground">Suggested next action</p>
            <p className="mt-0.5">{entry.reason.suggestedAction}</p>
          </div>
        </div>
      ) : (
        <div className="mt-2 rounded-lg border border-border/30 bg-muted/10 px-3 py-4 text-center text-muted-foreground" data-testid="empty-why-flagged">
          <p className="text-sm font-medium">{t("監視中", "Monitoring active")}</p>
          <p className="mt-1 text-[11px]">{t("フラグされたリクエストがないため、構造化理由は表示されません。", "No flagged requests — structured reasoning will appear when a request is selected.")}</p>
        </div>
      )}
    </div>
  );
}
