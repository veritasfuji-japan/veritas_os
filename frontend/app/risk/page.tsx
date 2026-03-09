"use client";

import Link from "next/link";
import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { useEffect, useMemo, useState } from "react";

interface RiskPoint {
  id: string;
  uncertainty: number;
  risk: number;
  timestamp: number;
}

interface TrendBucket {
  label: string;
  total: number;
  highRisk: number;
}

const STREAM_WINDOW_MS = 24 * 60 * 60 * 1000;
const ALERT_CLUSTER_THRESHOLD = 0.82;
const STREAM_TICK_MS = 2_000;
const MAX_POINTS = 480;

/**
 * NOTE: This page uses synthetic telemetry until a per-request risk API is available.
 * It is safe for UI/interaction validation only, and must not be used as evidence for
 * production incident response or compliance reporting.
 */
function createInitialPoints(now: number): RiskPoint[] {
  return Array.from({ length: 160 }, (_, index) => {
    const wave = (Math.sin(index * 0.42) + 1) / 2;
    const uncertainty = Math.min(1, Math.max(0.03, wave * 0.88 + (index % 5) * 0.02));
    const risk = Math.min(1, Math.max(0.04, ((Math.cos(index * 0.31) + 1) / 2) * 0.9));

    return {
      id: `seed-${index}`,
      uncertainty,
      risk,
      timestamp: now - (index / 160) * STREAM_WINDOW_MS,
    };
  });
}

function createStreamPoint(now: number): RiskPoint {
  const id = `${now}-${Math.random().toString(36).slice(2, 8)}`;
  const uncertainty = Math.random();
  const baseRisk = uncertainty * 0.65 + Math.random() * 0.35;
  const spike = Math.random() > 0.93 ? 0.15 : 0;

  return {
    id,
    uncertainty,
    risk: Math.min(1, baseRisk + spike),
    timestamp: now,
  };
}

function getCluster(point: RiskPoint): "critical" | "risky" | "uncertain" | "stable" {
  if (point.uncertainty >= ALERT_CLUSTER_THRESHOLD && point.risk >= ALERT_CLUSTER_THRESHOLD) {
    return "critical";
  }
  if (point.risk >= ALERT_CLUSTER_THRESHOLD) {
    return "risky";
  }
  if (point.uncertainty >= ALERT_CLUSTER_THRESHOLD) {
    return "uncertain";
  }
  return "stable";
}

function explainFlag(point: RiskPoint): string {
  const cluster = getCluster(point);
  if (cluster === "critical") {
    return "High uncertainty + high risk. Potential unsafe output with weak policy confidence.";
  }
  if (cluster === "risky") {
    return "Risk score is high despite lower uncertainty. Policy violation likelihood is elevated.";
  }
  if (cluster === "uncertain") {
    return "Uncertainty is high. Model behavior may drift or become unstable.";
  }
  return "Within expected safety envelope.";
}

function buildTrendBuckets(points: RiskPoint[], now: number): TrendBucket[] {
  const bucketMs = 3 * 60 * 60 * 1000;
  return Array.from({ length: 8 }, (_, index) => {
    const start = now - (8 - index) * bucketMs;
    const end = start + bucketMs;
    const segment = points.filter((point) => point.timestamp >= start && point.timestamp < end);
    const highRisk = segment.filter((point) => getCluster(point) === "critical").length;

    return {
      label: `${index * 3}-${(index + 1) * 3}h`,
      total: segment.length,
      highRisk,
    };
  });
}

export default function RiskIntelligencePage(): JSX.Element {
  const { t, language } = useI18n();
  const [points, setPoints] = useState<RiskPoint[]>(() => createInitialPoints(Date.now()));
  const [now, setNow] = useState<number>(Date.now());
  const [timeWindowHours, setTimeWindowHours] = useState<number>(24);
  const [selectedCluster, setSelectedCluster] = useState<"all" | "critical" | "risky" | "uncertain">("all");
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);

  useEffect(() => {
    const timer = window.setInterval(() => {
      const tick = Date.now();
      setNow(tick);
      setPoints((previous) => {
        return [...previous, createStreamPoint(tick)]
          .filter((point) => tick - point.timestamp <= STREAM_WINDOW_MS)
          .slice(-MAX_POINTS);
      });
    }, STREAM_TICK_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const visiblePoints = useMemo(() => {
    return points.filter((point) => now - point.timestamp <= timeWindowHours * 60 * 60 * 1000);
  }, [points, now, timeWindowHours]);

  const filteredPoints = useMemo(() => {
    if (selectedCluster === "all") {
      return visiblePoints;
    }
    return visiblePoints.filter((point) => getCluster(point) === selectedCluster);
  }, [visiblePoints, selectedCluster]);

  const clusterStats = useMemo(() => {
    const highRiskPoints = visiblePoints.filter((point) => getCluster(point) === "critical");
    const ratio = visiblePoints.length === 0 ? 0 : highRiskPoints.length / visiblePoints.length;
    return {
      ratio,
      count: highRiskPoints.length,
      alert: highRiskPoints.length >= 15 || ratio >= 0.08,
    };
  }, [visiblePoints]);

  const trend = useMemo(() => buildTrendBuckets(visiblePoints, now), [visiblePoints, now]);
  const previousHighRisk = trend.slice(0, 7).reduce((sum, bucket) => sum + bucket.highRisk, 0) / 7;
  const latestHighRisk = trend[7]?.highRisk ?? 0;
  const spikeDetected = latestHighRisk >= previousHighRisk * 1.8 && latestHighRisk >= 3;
  const unsafeBurst = latestHighRisk >= 6;

  const flaggedRequests = useMemo(() => {
    return visiblePoints
      .filter((point) => getCluster(point) !== "stable")
      .sort((left, right) => right.risk + right.uncertainty - (left.risk + left.uncertainty))
      .slice(0, 20);
  }, [visiblePoints]);

  const selectedPoint = flaggedRequests.find((item) => item.id === selectedPointId) ?? flaggedRequests[0] ?? null;

  return (
    <div className="space-y-6">
      <Card
        title="Risk Intelligence"
        description={t("可視化だけでなく、ドリルダウン・原因説明・統治アクションまでつなぐ分析面です。", "From visualization to action: drilldown, root-cause explanation, and governance pathways.")}
        variant="glass"
        accent="danger"
        className="border-danger/15"
      >
        <div className="flex flex-wrap gap-2 text-xs">
          <Link href="/console" className="rounded border border-border/60 px-2 py-1 hover:bg-muted/40">Decision</Link>
          <Link href="/audit" className="rounded border border-border/60 px-2 py-1 hover:bg-muted/40">TrustLog</Link>
          <Link href="/governance" className="rounded border border-border/60 px-2 py-1 hover:bg-muted/40">Governance</Link>
        </div>
      </Card>

      <Card title="Real-time Risk Heatmap" titleSize="md" variant="elevated">
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("ステータス", "Status")}</p>
              <p className={`mt-0.5 font-semibold ${clusterStats.alert ? "text-danger" : "text-success"}`}>
                {clusterStats.alert ? "Cluster Alert" : "Normal"}
              </p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("高リスク", "High-risk")}</p>
              <p className="mt-0.5 font-mono font-semibold text-foreground">{clusterStats.count} / {visiblePoints.length}</p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("クラスタ率", "Cluster rate")}</p>
              <p className="mt-0.5 font-mono font-semibold text-foreground">{(clusterStats.ratio * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("最終更新", "Updated")}</p>
              <p className="mt-0.5 font-mono text-[11px] font-semibold text-foreground" aria-live="polite">
                {new Date(now).toLocaleTimeString(language === "ja" ? "ja-JP" : "en-US", { hour12: false })}
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
            <label className="space-y-1">
              <span className="text-muted-foreground">Time window</span>
              <select className="block rounded border border-border bg-background px-2 py-1" value={timeWindowHours} onChange={(event) => setTimeWindowHours(Number(event.target.value))}>
                <option value={1}>1h</option>
                <option value={6}>6h</option>
                <option value={12}>12h</option>
                <option value={24}>24h</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground">Cluster drilldown</span>
              <select className="block rounded border border-border bg-background px-2 py-1" value={selectedCluster} onChange={(event) => setSelectedCluster(event.target.value as "all" | "critical" | "risky" | "uncertain")}>
                <option value="all">all points</option>
                <option value="critical">critical cluster</option>
                <option value="risky">high risk only</option>
                <option value="uncertain">high uncertainty only</option>
              </select>
            </label>
          </div>

          <div className="rounded-xl border border-border/50 bg-muted/10 p-5">
            <div className="relative mx-auto h-[380px] w-full max-w-5xl">
              <svg viewBox="0 0 100 100" className="h-full w-full" aria-label="Scatter plot of request uncertainty and risk from the last 24 hours" role="img">
                <defs>
                  <linearGradient id="riskGradient" x1="0" y1="100" x2="100" y2="0">
                    <stop offset="0%" stopColor="hsl(var(--ds-color-primary) / 0.12)" />
                    <stop offset="50%" stopColor="hsl(var(--ds-color-warning) / 0.18)" />
                    <stop offset="100%" stopColor="hsl(var(--ds-color-danger) / 0.25)" />
                  </linearGradient>
                </defs>
                <rect x="0" y="0" width="100" height="100" fill="url(#riskGradient)" rx="2" />

                {[20, 40, 60, 80].map((line) => (
                  <g key={line}>
                    <line x1={line} y1={0} x2={line} y2={100} stroke="hsl(var(--ds-color-border) / 0.5)" strokeWidth="0.25" />
                    <line x1={0} y1={line} x2={100} y2={line} stroke="hsl(var(--ds-color-border) / 0.5)" strokeWidth="0.25" />
                  </g>
                ))}

                {filteredPoints.map((point) => {
                  const x = point.uncertainty * 100;
                  const y = (1 - point.risk) * 100;
                  const cluster = getCluster(point);
                  const isSelected = selectedPointId === point.id;
                  const fill = cluster === "critical" ? "hsl(var(--destructive))" : "hsl(var(--primary) / 0.82)";
                  return (
                    <circle
                      key={point.id}
                      cx={x}
                      cy={y}
                      r={isSelected ? 1.6 : 1.1}
                      fill={fill}
                      opacity={cluster === "critical" ? 0.95 : 0.72}
                      onClick={() => setSelectedPointId(point.id)}
                    >
                      <title>{`ID:${point.id} | ${explainFlag(point)}`}</title>
                    </circle>
                  );
                })}
              </svg>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
              <p className="font-semibold">Policy drift</p>
              <p className="mt-1 text-muted-foreground">Recent high-risk ratio is rising versus baseline. Review policy thresholds and blocked categories.</p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
              <p className="font-semibold">Unsafe burst</p>
              <p className="mt-1 text-muted-foreground">A short-term concentration of critical events may indicate prompt injection campaign or rollout regression.</p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
              <p className="font-semibold">Unstable output cluster</p>
              <p className="mt-1 text-muted-foreground">High uncertainty clusters can precede trust degradation. Triage model slice and memory retrieval quality.</p>
            </div>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
              <p className="mb-2 font-semibold">Trend / Spike / Burst</p>
              <div className="flex items-end gap-2" aria-label="trend chart">
                {trend.map((bucket) => (
                  <button
                    type="button"
                    key={bucket.label}
                    className="flex flex-1 flex-col items-center gap-1"
                    onClick={() => setSelectedCluster(bucket.highRisk > 0 ? "critical" : "all")}
                  >
                    <span className="w-full rounded bg-primary/20" style={{ height: `${Math.max(8, bucket.total * 2)}px` }} />
                    <span className="text-[10px] text-muted-foreground">{bucket.label}</span>
                  </button>
                ))}
              </div>
              <p className="mt-2 text-muted-foreground">
                {spikeDetected ? "Spike detected." : "No significant spike."} {unsafeBurst ? "Unsafe burst active." : "Burst within normal band."}
              </p>
            </div>

            <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
              <p className="mb-2 font-semibold">Flagged requests</p>
              <ul className="max-h-56 space-y-2 overflow-auto pr-1">
                {flaggedRequests.map((request) => (
                  <li key={request.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedPointId(request.id)}
                      className="w-full rounded border border-border/40 px-2 py-1 text-left hover:bg-muted/30"
                    >
                      <p className="font-mono text-[10px]">{request.id}</p>
                      <p className="text-muted-foreground">risk {request.risk.toFixed(2)} / uncertainty {request.uncertainty.toFixed(2)}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
            <p className="font-semibold">Why flagged</p>
            {selectedPoint ? (
              <div className="mt-2 space-y-1">
                <p className="font-mono text-[10px]">{selectedPoint.id}</p>
                <p className="text-muted-foreground">{explainFlag(selectedPoint)}</p>
                <p className="text-muted-foreground">What to do next: open Decision for immediate mitigation, verify in TrustLog, then enforce policy updates in Governance.</p>
              </div>
            ) : (
              <p className="mt-2 text-muted-foreground">No flagged requests in this window.</p>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
