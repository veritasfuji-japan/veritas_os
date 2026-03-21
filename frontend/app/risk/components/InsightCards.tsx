"use client";

import { memo } from "react";
import Link from "next/link";

interface InsightCardsProps {
  clusterRatio: number;
  clusterCount: number;
  filteredPointsCount: number;
  unsafeBurst: boolean;
  latestHighRisk: number;
  uncertainCount: number;
}


export const InsightCards = memo(function InsightCards({ clusterRatio, clusterCount, filteredPointsCount, unsafeBurst, latestHighRisk, uncertainCount }: InsightCardsProps): JSX.Element {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      <div className={`rounded-lg border p-3 text-xs ${clusterRatio >= 0.05 ? "border-warning/40 bg-warning/5" : "border-border/50 bg-background/60"}`}>
        <p className="font-semibold">Policy drift</p>
        <p className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">Why it matters:</span> Rising high-risk ratio ({(clusterRatio * 100).toFixed(1)}%) suggests policy thresholds may no longer match current traffic patterns.
        </p>
        <p className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">Impact scope:</span> {clusterCount} critical requests in current window across {filteredPointsCount} total points.
        </p>
        <Link href="/governance" className="mt-2 inline-block rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40">
          Review thresholds in Governance →
        </Link>
      </div>
      <div className={`rounded-lg border p-3 text-xs ${unsafeBurst ? "border-danger/40 bg-danger/5" : "border-border/50 bg-background/60"}`}>
        <p className="font-semibold">Unsafe burst</p>
        <p className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">Why it matters:</span> {unsafeBurst ? "Active burst detected — ≥6 critical events in the latest 3h window may indicate prompt injection or rollout regression." : "No active burst. Critical event concentration is within normal bounds."}
        </p>
        <p className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">Impact scope:</span> {latestHighRisk} critical events in latest 3h bucket.
        </p>
        <Link href="/console" className="mt-2 inline-block rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40">
          Investigate in Decision →
        </Link>
      </div>
      <div className={`rounded-lg border p-3 text-xs ${uncertainCount >= 10 ? "border-info/40 bg-info/5" : "border-border/50 bg-background/60"}`}>
        <p className="font-semibold">Unstable output cluster</p>
        <p className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">Why it matters:</span> High-uncertainty clusters ({uncertainCount} points) can precede trust degradation and model drift.
        </p>
        <p className="mt-1 text-muted-foreground">
          <span className="font-medium text-foreground">Impact scope:</span> May affect retrieval quality and output consistency for end users.
        </p>
        <Link href="/audit" className="mt-2 inline-block rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40">
          Check stability in TrustLog →
        </Link>
      </div>
    </div>
  );
});
