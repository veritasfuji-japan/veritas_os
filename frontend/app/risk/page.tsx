"use client";

import Link from "next/link";
import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { useEffect, useMemo, useState } from "react";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type ClusterKind = "critical" | "risky" | "uncertain" | "stable";
type Severity = "critical" | "high" | "medium" | "low";
type RequestStatus = "active" | "mitigated" | "investigating" | "new";

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

/** Structured reason for flagging a request. */
interface FlagReason {
  policyConfidence: number;
  unstableOutputSignal: boolean;
  retrievalAnomaly: boolean;
  summary: string;
  suggestedAction: string;
}

/** Enriched view of a flagged request used in drilldown and lists. */
interface FlaggedEntry {
  point: RiskPoint;
  cluster: ClusterKind;
  severity: Severity;
  status: RequestStatus;
  reason: FlagReason;
  relatedPolicyHits: string[];
  stageAnomalies: string[];
}

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const STREAM_WINDOW_MS = 24 * 60 * 60 * 1000;
const ALERT_CLUSTER_THRESHOLD = 0.82;
const STREAM_TICK_MS = 2_000;
const MAX_POINTS = 480;

const SEVERITY_CLASSES: Record<Severity, string> = {
  critical: "bg-danger/15 text-danger border-danger/30",
  high: "bg-warning/15 text-warning border-warning/30",
  medium: "bg-info/15 text-info border-info/30",
  low: "bg-muted/20 text-muted-foreground border-border/40",
};

const STATUS_LABELS: Record<RequestStatus, string> = {
  active: "Active",
  mitigated: "Mitigated",
  investigating: "Investigating",
  new: "New",
};

/* ------------------------------------------------------------------ */
/*  Data helpers                                                       */
/* ------------------------------------------------------------------ */

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

function getCluster(point: RiskPoint): ClusterKind {
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

function deriveSeverity(point: RiskPoint): Severity {
  const combined = point.risk * 0.6 + point.uncertainty * 0.4;
  if (combined >= 0.85) return "critical";
  if (combined >= 0.7) return "high";
  if (combined >= 0.5) return "medium";
  return "low";
}

function deriveStatus(point: RiskPoint): RequestStatus {
  if (point.id.startsWith("seed-")) {
    const idx = Number(point.id.replace("seed-", ""));
    if (idx % 7 === 0) return "mitigated";
    if (idx % 5 === 0) return "investigating";
  }
  return "new";
}

function buildFlagReason(point: RiskPoint): FlagReason {
  const cluster = getCluster(point);
  const policyConfidence = Math.max(0, 1 - point.risk * 0.9 - point.uncertainty * 0.15);
  const unstableOutputSignal = point.uncertainty >= 0.75;
  const retrievalAnomaly = point.risk >= 0.7 && point.uncertainty >= 0.6;

  let summary: string;
  let suggestedAction: string;

  if (cluster === "critical") {
    summary = "High uncertainty combined with high risk score. Policy confidence is low and output stability cannot be guaranteed.";
    suggestedAction = "Escalate to Decision Console for immediate review; verify trust chain in TrustLog.";
  } else if (cluster === "risky") {
    summary = "Risk score exceeds threshold. Policy violation likelihood is elevated despite moderate uncertainty.";
    suggestedAction = "Check Decision Console for policy hit details; review Governance thresholds.";
  } else if (cluster === "uncertain") {
    summary = "Uncertainty is high. Model behavior may drift or produce unstable outputs.";
    suggestedAction = "Monitor in TrustLog for output consistency; consider tightening retrieval quality checks.";
  } else {
    summary = "Within expected safety envelope.";
    suggestedAction = "No immediate action required.";
  }

  return { policyConfidence, unstableOutputSignal, retrievalAnomaly, summary, suggestedAction };
}

function deriveRelatedPolicyHits(point: RiskPoint): string[] {
  const hits: string[] = [];
  if (point.risk >= 0.82) hits.push("content-safety-v2");
  if (point.uncertainty >= 0.82) hits.push("output-stability-check");
  if (point.risk >= 0.7 && point.uncertainty >= 0.6) hits.push("retrieval-quality-gate");
  if (point.risk >= 0.9) hits.push("prompt-injection-shield");
  return hits;
}

function deriveStageAnomalies(point: RiskPoint): string[] {
  const anomalies: string[] = [];
  if (point.uncertainty >= 0.75) anomalies.push("LLM output variance high");
  if (point.risk >= 0.8) anomalies.push("Safety gate triggered");
  if (point.risk >= 0.7 && point.uncertainty >= 0.6) anomalies.push("Retrieval confidence low");
  if (point.risk >= 0.9) anomalies.push("Post-processing filter activated");
  return anomalies;
}

function enrichFlaggedEntry(point: RiskPoint): FlaggedEntry {
  return {
    point,
    cluster: getCluster(point),
    severity: deriveSeverity(point),
    status: deriveStatus(point),
    reason: buildFlagReason(point),
    relatedPolicyHits: deriveRelatedPolicyHits(point),
    stageAnomalies: deriveStageAnomalies(point),
  };
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

function bucketMeaning(bucket: TrendBucket): string {
  if (bucket.highRisk >= 6) return "Unsafe burst — critical concentration detected";
  if (bucket.highRisk >= 3) return "Elevated risk — multiple critical events";
  if (bucket.highRisk > 0) return "Low-level risk events present";
  if (bucket.total === 0) return "No activity in this window";
  return "Normal operation";
}

/* ------------------------------------------------------------------ */
/*  Scatter plot fill helpers                                          */
/* ------------------------------------------------------------------ */

function pointFill(cluster: ClusterKind): string {
  if (cluster === "critical") return "hsl(var(--destructive))";
  if (cluster === "risky") return "hsl(var(--ds-color-warning))";
  if (cluster === "uncertain") return "hsl(var(--ds-color-info))";
  return "hsl(var(--primary) / 0.82)";
}

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export default function RiskIntelligencePage(): JSX.Element {
  const { t, language } = useI18n();
  const [points, setPoints] = useState<RiskPoint[]>(() => createInitialPoints(Date.now()));
  const [now, setNow] = useState<number>(Date.now());
  const [timeWindowHours, setTimeWindowHours] = useState<number>(24);
  const [selectedCluster, setSelectedCluster] = useState<"all" | "critical" | "risky" | "uncertain">("all");
  const [selectedPointId, setSelectedPointId] = useState<string | null>(null);
  const [hoveredPointId, setHoveredPointId] = useState<string | null>(null);

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

  /* ---------- derived data ---------- */

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

  const flaggedEntries = useMemo(() => {
    return visiblePoints
      .filter((point) => getCluster(point) !== "stable")
      .sort((left, right) => right.risk + right.uncertainty - (left.risk + left.uncertainty))
      .slice(0, 20)
      .map(enrichFlaggedEntry);
  }, [visiblePoints]);

  const selectedEntry = flaggedEntries.find((entry) => entry.point.id === selectedPointId) ?? flaggedEntries[0] ?? null;

  const hoveredPoint = hoveredPointId ? visiblePoints.find((point) => point.id === hoveredPointId) ?? null : null;

  /* ---------- render ---------- */

  return (
    <div className="space-y-6">
      {/* ── Header card with cross-navigation ── */}
      <Card
        title="Risk Intelligence"
        description={t("可視化だけでなく、ドリルダウン・原因説明・統治アクションまでつなぐ分析面です。", "From visualization to action: drilldown, root-cause explanation, and governance pathways.")}
        variant="glass"
        accent="danger"
        className="border-danger/15"
      >
        <div className="flex flex-wrap gap-2 text-xs">
          <Link href="/console" className="rounded border border-border/60 px-2 py-1 hover:bg-muted/40 inline-flex items-center gap-1">
            <span aria-hidden>⚡</span> Decision
          </Link>
          <Link href="/audit" className="rounded border border-border/60 px-2 py-1 hover:bg-muted/40 inline-flex items-center gap-1">
            <span aria-hidden>📋</span> TrustLog
          </Link>
          <Link href="/governance" className="rounded border border-border/60 px-2 py-1 hover:bg-muted/40 inline-flex items-center gap-1">
            <span aria-hidden>🛡</span> Governance
          </Link>
        </div>
      </Card>

      {/* ── Heatmap section ── */}
      <Card title="Real-time Risk Heatmap" titleSize="md" variant="elevated">
        <div className="space-y-5">
          {/* status metrics */}
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

          {/* filter controls */}
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

          {/* scatter plot with enhanced interactivity */}
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

                {/* axis labels */}
                <text x="50" y="99" textAnchor="middle" fontSize="2.5" fill="hsl(var(--ds-color-muted-foreground))">Uncertainty →</text>
                <text x="1.5" y="50" textAnchor="middle" fontSize="2.5" fill="hsl(var(--ds-color-muted-foreground))" transform="rotate(-90,1.5,50)">Risk →</text>

                {/* grid lines */}
                {[20, 40, 60, 80].map((line) => (
                  <g key={line}>
                    <line x1={line} y1={0} x2={line} y2={100} stroke="hsl(var(--ds-color-border) / 0.5)" strokeWidth="0.25" />
                    <line x1={0} y1={line} x2={100} y2={line} stroke="hsl(var(--ds-color-border) / 0.5)" strokeWidth="0.25" />
                  </g>
                ))}

                {/* danger zone indicator */}
                <rect x="82" y="0" width="18" height="18" fill="hsl(var(--destructive) / 0.08)" rx="1" />
                <text x="91" y="10" textAnchor="middle" fontSize="2" fill="hsl(var(--destructive) / 0.5)">CRITICAL</text>

                {/* data points */}
                {filteredPoints.map((point) => {
                  const x = point.uncertainty * 100;
                  const y = (1 - point.risk) * 100;
                  const cluster = getCluster(point);
                  const isSelected = selectedPointId === point.id;
                  const isHovered = hoveredPointId === point.id;
                  const fill = pointFill(cluster);
                  return (
                    <g key={point.id}>
                      {isSelected && (
                        <circle cx={x} cy={y} r="2.8" fill="none" stroke={fill} strokeWidth="0.4" opacity="0.6" />
                      )}
                      <circle
                        cx={x}
                        cy={y}
                        r={isSelected ? 1.6 : isHovered ? 1.4 : 1.1}
                        fill={fill}
                        opacity={cluster === "critical" ? 0.95 : cluster === "risky" ? 0.85 : 0.72}
                        className="cursor-pointer"
                        onClick={() => setSelectedPointId(point.id)}
                        onMouseEnter={() => setHoveredPointId(point.id)}
                        onMouseLeave={() => setHoveredPointId(null)}
                      >
                        <title>{`ID: ${point.id}\nRisk: ${point.risk.toFixed(2)} | Uncertainty: ${point.uncertainty.toFixed(2)}\nCluster: ${cluster}`}</title>
                      </circle>
                    </g>
                  );
                })}
              </svg>

              {/* Hover summary tooltip */}
              {hoveredPoint && (
                <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-xs rounded-lg border border-border/60 bg-background/95 px-3 py-2 text-xs shadow-lg" data-testid="hover-summary">
                  <p className="font-mono text-[10px] text-muted-foreground">{hoveredPoint.id}</p>
                  <p className="mt-0.5"><span className="text-muted-foreground">Risk:</span> <span className="font-semibold">{hoveredPoint.risk.toFixed(2)}</span> · <span className="text-muted-foreground">Uncertainty:</span> <span className="font-semibold">{hoveredPoint.uncertainty.toFixed(2)}</span></p>
                  <p className="mt-0.5 text-muted-foreground">Cluster: <span className="font-semibold">{getCluster(hoveredPoint)}</span></p>
                </div>
              )}
            </div>
          </div>

          {/* ── Insight cards: Policy drift / Unsafe burst / Unstable cluster ── */}
          <div className="grid gap-3 md:grid-cols-3">
            <div className={`rounded-lg border p-3 text-xs ${clusterStats.ratio >= 0.05 ? "border-warning/40 bg-warning/5" : "border-border/50 bg-background/60"}`}>
              <p className="font-semibold">Policy drift</p>
              <p className="mt-1 text-muted-foreground">
                <span className="font-medium text-foreground">Why it matters:</span> Rising high-risk ratio ({(clusterStats.ratio * 100).toFixed(1)}%) suggests policy thresholds may no longer match current traffic patterns.
              </p>
              <p className="mt-1 text-muted-foreground">
                <span className="font-medium text-foreground">Impact scope:</span> {clusterStats.count} critical requests in current window across {filteredPoints.length} total points.
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
            <div className={`rounded-lg border p-3 text-xs ${visiblePoints.filter((p) => getCluster(p) === "uncertain").length >= 10 ? "border-info/40 bg-info/5" : "border-border/50 bg-background/60"}`}>
              <p className="font-semibold">Unstable output cluster</p>
              <p className="mt-1 text-muted-foreground">
                <span className="font-medium text-foreground">Why it matters:</span> High-uncertainty clusters ({visiblePoints.filter((p) => getCluster(p) === "uncertain").length} points) can precede trust degradation and model drift.
              </p>
              <p className="mt-1 text-muted-foreground">
                <span className="font-medium text-foreground">Impact scope:</span> May affect retrieval quality and output consistency for end users.
              </p>
              <Link href="/audit" className="mt-2 inline-block rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40">
                Check stability in TrustLog →
              </Link>
            </div>
          </div>

          {/* ── Trend / Spike / Burst + Flagged requests ── */}
          <div className="grid gap-4 lg:grid-cols-2">
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
                      onClick={() => setSelectedCluster(bucket.highRisk > 0 ? "critical" : "all")}
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

            {/* ── Flagged requests (enhanced) ── */}
            <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs">
              <p className="mb-2 font-semibold">Flagged requests</p>
              {flaggedEntries.length === 0 ? (
                <div className="rounded-lg border border-border/30 bg-muted/10 px-3 py-4 text-center text-muted-foreground" data-testid="empty-flagged">
                  <p className="text-sm font-medium">{t("監視中", "Monitoring active")}</p>
                  <p className="mt-1 text-[11px]">{t("現在フラグされたリクエストはありません。リアルタイムで監視を継続しています。", "No flagged requests in this window. Real-time monitoring continues.")}</p>
                </div>
              ) : (
                <ul className="max-h-64 space-y-2 overflow-auto pr-1">
                  {flaggedEntries.map((entry) => (
                    <li key={entry.point.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPointId(entry.point.id)}
                        className={`w-full rounded border px-2 py-1.5 text-left hover:bg-muted/30 ${selectedPointId === entry.point.id ? "ring-1 ring-primary/50 bg-muted/20" : "border-border/40"}`}
                      >
                        <div className="flex items-center justify-between">
                          <p className="font-mono text-[10px]">{entry.point.id}</p>
                          <div className="flex items-center gap-1">
                            <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${SEVERITY_CLASSES[entry.severity]}`}>
                              {entry.severity}
                            </span>
                            <span className="rounded bg-muted/40 px-1 py-0.5 text-[9px]">{STATUS_LABELS[entry.status]}</span>
                          </div>
                        </div>
                        <p className="mt-0.5 text-muted-foreground">risk {entry.point.risk.toFixed(2)} / uncertainty {entry.point.uncertainty.toFixed(2)}</p>
                        <div className="mt-1 flex gap-1">
                          <Link href={`/console?request_id=${encodeURIComponent(entry.point.id)}`} className="rounded border border-border/50 px-1.5 py-0.5 text-[9px] hover:bg-muted/40" onClick={(event) => event.stopPropagation()}>
                            Open in Decision
                          </Link>
                          <Link href={`/audit?request_id=${encodeURIComponent(entry.point.id)}`} className="rounded border border-border/50 px-1.5 py-0.5 text-[9px] hover:bg-muted/40" onClick={(event) => event.stopPropagation()}>
                            Open in TrustLog
                          </Link>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {/* ── Drilldown panel ── */}
          <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs" data-testid="drilldown-panel">
            <p className="font-semibold">Drilldown panel</p>
            {selectedEntry ? (
              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div className="space-y-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Request ID / Seed</p>
                    <p className="font-mono text-[11px]">{selectedEntry.point.id}</p>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <p className="text-[10px] font-semibold uppercase text-muted-foreground">Uncertainty</p>
                      <p className="font-mono font-semibold">{selectedEntry.point.uncertainty.toFixed(3)}</p>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold uppercase text-muted-foreground">Risk score</p>
                      <p className="font-mono font-semibold">{selectedEntry.point.risk.toFixed(3)}</p>
                    </div>
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Severity / Status</p>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className={`rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase ${SEVERITY_CLASSES[selectedEntry.severity]}`}>
                        {selectedEntry.severity}
                      </span>
                      <span className="rounded bg-muted/40 px-1 py-0.5 text-[9px]">{STATUS_LABELS[selectedEntry.status]}</span>
                    </div>
                  </div>
                </div>
                <div className="space-y-2">
                  <div>
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Related policy hits</p>
                    {selectedEntry.relatedPolicyHits.length > 0 ? (
                      <ul className="mt-0.5 space-y-0.5">
                        {selectedEntry.relatedPolicyHits.map((hit) => (
                          <li key={hit} className="rounded bg-warning/10 px-1.5 py-0.5 text-[10px]">⚡ {hit}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-muted-foreground">No policy hits</p>
                    )}
                  </div>
                  <div>
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Stage anomalies</p>
                    {selectedEntry.stageAnomalies.length > 0 ? (
                      <ul className="mt-0.5 space-y-0.5">
                        {selectedEntry.stageAnomalies.map((anomaly) => (
                          <li key={anomaly} className="rounded bg-danger/10 px-1.5 py-0.5 text-[10px]">⚠ {anomaly}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-muted-foreground">No anomalies detected</p>
                    )}
                  </div>
                </div>
                <div className="md:col-span-2 flex flex-wrap gap-1 border-t border-border/30 pt-2">
                  <Link href={`/console?request_id=${encodeURIComponent(selectedEntry.point.id)}`} className="rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40 inline-flex items-center gap-1">
                    <span aria-hidden>⚡</span> Open in Decision
                  </Link>
                  <Link href={`/audit?request_id=${encodeURIComponent(selectedEntry.point.id)}`} className="rounded border border-border/60 px-2 py-0.5 text-[10px] font-semibold hover:bg-muted/40 inline-flex items-center gap-1">
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

          {/* ── Structured why-flagged ── */}
          <div className="rounded-lg border border-border/50 bg-background/60 p-3 text-xs" data-testid="why-flagged">
            <p className="font-semibold">Why flagged</p>
            {selectedEntry ? (
              <div className="mt-2 space-y-3">
                <p className="font-mono text-[10px] text-muted-foreground">{selectedEntry.point.id}</p>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-lg border border-border/40 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Policy confidence</p>
                    <p className={`font-mono font-semibold ${selectedEntry.reason.policyConfidence < 0.3 ? "text-danger" : selectedEntry.reason.policyConfidence < 0.6 ? "text-warning" : "text-success"}`}>
                      {(selectedEntry.reason.policyConfidence * 100).toFixed(0)}%
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/40 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Unstable output</p>
                    <p className={`font-semibold ${selectedEntry.reason.unstableOutputSignal ? "text-danger" : "text-success"}`}>
                      {selectedEntry.reason.unstableOutputSignal ? "Detected" : "Stable"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/40 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Retrieval anomaly</p>
                    <p className={`font-semibold ${selectedEntry.reason.retrievalAnomaly ? "text-warning" : "text-success"}`}>
                      {selectedEntry.reason.retrievalAnomaly ? "Anomaly" : "Normal"}
                    </p>
                  </div>
                  <div className="rounded-lg border border-border/40 px-2 py-1.5">
                    <p className="text-[10px] font-semibold uppercase text-muted-foreground">Cluster</p>
                    <p className="font-semibold">{selectedEntry.cluster}</p>
                  </div>
                </div>
                <div className="rounded-lg border border-border/40 bg-muted/5 px-2 py-1.5">
                  <p className="text-[10px] font-semibold uppercase text-muted-foreground">Analysis</p>
                  <p className="mt-0.5 text-muted-foreground">{selectedEntry.reason.summary}</p>
                </div>
                <div className="rounded-lg border border-primary/30 bg-primary/5 px-2 py-1.5">
                  <p className="text-[10px] font-semibold uppercase text-muted-foreground">Suggested next action</p>
                  <p className="mt-0.5">{selectedEntry.reason.suggestedAction}</p>
                </div>
              </div>
            ) : (
              <div className="mt-2 rounded-lg border border-border/30 bg-muted/10 px-3 py-4 text-center text-muted-foreground" data-testid="empty-why-flagged">
                <p className="text-sm font-medium">{t("監視中", "Monitoring active")}</p>
                <p className="mt-1 text-[11px]">{t("フラグされたリクエストがないため、構造化理由は表示されません。", "No flagged requests — structured reasoning will appear when a request is selected.")}</p>
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
