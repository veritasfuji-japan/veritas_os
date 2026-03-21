"use client";

import type { TrendBucket } from "../risk-types";
import { bucketMeaning } from "../data-helpers";

interface TrendChartProps {
  trend: TrendBucket[];
  spikeDetected: boolean;
  unsafeBurst: boolean;
  onSelectCluster: (cluster: "all" | "critical") => void;
}

export function TrendChart({ trend, spikeDetected, unsafeBurst, onSelectCluster }: TrendChartProps): JSX.Element {
  return (
    <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
      <p className="mb-2 font-semibold">Trend / Spike / Burst</p>
      <div className="flex items-end gap-2" aria-label="trend chart">
        {trend.map((bucket) => {
          const isLatest = bucket.label === trend[7]?.label;
          return (
            <button
              type="button"
              key={bucket.label}
              className={`flex flex-1 flex-col items-center gap-1 rounded px-0.5 py-0.5 ${isLatest ? "ring-1 ring-primary/40" : ""}`}
              title={bucketMeaning(bucket)}
              onClick={() => onSelectCluster(bucket.highRisk > 0 ? "critical" : "all")}
            >
              <div className="flex w-full flex-col items-center">
                {bucket.highRisk > 0 && (
                  <span className="w-full rounded-t bg-danger/40" style={{ height: `${Math.max(4, bucket.highRisk * 4)}px` }} />
                )}
                <span className="w-full rounded bg-primary/20" style={{ height: `${Math.max(8, bucket.total * 2)}px` }} />
              </div>
              <span className="text-[10px] text-muted-foreground">{bucket.label}</span>
              {bucket.highRisk > 0 && <span className="text-[9px] font-semibold text-danger">{bucket.highRisk}</span>}
            </button>
          );
        })}
      </div>
      <div className="mt-2 space-y-1 text-muted-foreground">
        <p>{spikeDetected ? "⚠ Spike detected — latest bucket shows 1.8× above average." : "No significant spike."}</p>
        <p>{unsafeBurst ? "🔴 Unsafe burst active — ≥6 critical events in latest window." : "Burst within normal band."}</p>
      </div>
    </div>
  );
}
