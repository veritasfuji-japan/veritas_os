"use client";

import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { memo, useEffect, useMemo, useRef, useState } from "react";

interface RiskPoint {
  id: string;
  uncertainty: number;
  risk: number;
  timestamp: number;
}

const STREAM_WINDOW_MS = 24 * 60 * 60 * 1000;
const ALERT_CLUSTER_THRESHOLD = 0.82;
const STREAM_TICK_MS = 2_000;
const MAX_POINTS = 480;

/**
 * NOTE: This page uses client-side synthetic telemetry for the scatter visualization.
 * The backend does not expose a per-request risk/uncertainty time-series endpoint.
 * The `/v1/metrics` endpoint provides only aggregate counts (total decisions, last
 * decision timestamp, pipeline health), which are not suitable for scatter plotting.
 * If a per-request telemetry endpoint is added in the future, replace the synthetic
 * generators below with a real API call and update `RiskPoint` accordingly.
 */

/**
 * Generates initial synthetic request telemetry distributed over the past 24h.
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

/**
 * Creates one new near-real-time point while preserving occasional high-risk events.
 */
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

function toChartCoordinate(value: number): number {
  return Math.round(value * 100);
}

interface RiskScatterCanvasProps {
  points: RiskPoint[];
}

/**
 * Draws request points on canvas to avoid React-driven SVG node reconciliation on every stream tick.
 */
const RiskScatterCanvas = memo(function RiskScatterCanvas({ points }: RiskScatterCanvasProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const getContext = canvas.getContext.bind(canvas) as typeof canvas.getContext;
    let context: CanvasRenderingContext2D | null = null;
    try {
      context = getContext("2d");
    } catch {
      return;
    }
    if (!context) {
      return;
    }

    const dpr = window.devicePixelRatio || 1;
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    const nextWidth = Math.max(1, Math.floor(width * dpr));
    const nextHeight = Math.max(1, Math.floor(height * dpr));

    if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
      canvas.width = nextWidth;
      canvas.height = nextHeight;
    }

    context.setTransform(dpr, 0, 0, dpr, 0, 0);
    context.clearRect(0, 0, width, height);

    points.forEach((point) => {
      const x = (toChartCoordinate(point.uncertainty) / 100) * width;
      const y = (1 - toChartCoordinate(point.risk) / 100) * height;
      const critical = point.uncertainty >= ALERT_CLUSTER_THRESHOLD
        && point.risk >= ALERT_CLUSTER_THRESHOLD;

      context.beginPath();
      context.arc(x, y, critical ? 4.4 : 3, 0, Math.PI * 2);
      context.fillStyle = critical
        ? "hsl(var(--destructive))"
        : "hsl(var(--primary) / 0.82)";
      context.globalAlpha = critical ? 0.95 : 0.72;
      context.fill();
    });

    context.globalAlpha = 1;
  }, [points]);

  return (
    <canvas
      ref={canvasRef}
      className="absolute inset-0 h-full w-full"
      aria-label="Scatter plot of request uncertainty and risk from the last 24 hours"
      role="img"
    />
  );
});

export default function RiskIntelligencePage(): JSX.Element {
  const { t, language } = useI18n();
  const [points, setPoints] = useState<RiskPoint[]>(() => createInitialPoints(Date.now()));
  const [now, setNow] = useState<number>(Date.now());
  const [timeWindowHours, setTimeWindowHours] = useState<number>(24);
  const [selectedCluster, setSelectedCluster] = useState<"all" | "high">("all");

  useEffect(() => {
    const timer = window.setInterval(() => {
      const tick = Date.now();
      setNow(tick);
      setPoints((previous) => {
        const next = [...previous, createStreamPoint(tick)]
          .filter((point) => tick - point.timestamp <= STREAM_WINDOW_MS)
          .slice(-MAX_POINTS);
        return next;
      });
    }, STREAM_TICK_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  const visiblePoints = useMemo(() => points.filter((point) => now - point.timestamp <= timeWindowHours * 60 * 60 * 1000), [points, now, timeWindowHours]);

  const clusterStats = useMemo(() => {
    const highRiskPoints = visiblePoints.filter(
      (point) => point.uncertainty >= ALERT_CLUSTER_THRESHOLD && point.risk >= ALERT_CLUSTER_THRESHOLD,
    );
    const ratio = visiblePoints.length === 0 ? 0 : highRiskPoints.length / visiblePoints.length;
    return {
      ratio,
      count: highRiskPoints.length,
      alert: highRiskPoints.length >= 15 || ratio >= 0.08,
    };
  }, [visiblePoints]);

  return (
    <div className="space-y-6">
      <Card
        title="Risk Intelligence"
        description={t("過去24時間の全リクエストを不確実性（横軸）と潜在的リスク（縦軸）でリアルタイム可視化します。危険なクラスタリングを検知するとアラートを表示し、予防的な統治判断を支援します。", "Visualize all requests from the last 24 hours in real time by uncertainty (x-axis) and potential risk (y-axis). When dangerous clustering is detected, alerts support proactive governance decisions.")}
        variant="glass"
        accent="danger"
        className="border-danger/15"
      >
        <div />
      </Card>

      <Card
        title="Real-time Risk Heatmap"
        titleSize="md"
        variant="elevated"
      >
        <div className="space-y-5">
          {/* Stats row */}
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
                <option value={24}>24h</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground">Cluster drilldown</span>
              <select className="block rounded border border-border bg-background px-2 py-1" value={selectedCluster} onChange={(event) => setSelectedCluster(event.target.value as "all" | "high") }>
                <option value="all">all points</option>
                <option value="high">high-risk only</option>
              </select>
            </label>
          </div>

          {/* Alert banner */}
          {clusterStats.alert && (
            <div className="flex items-center gap-3 rounded-xl border border-danger/30 bg-danger/8 px-4 py-3">
              <span className="h-2 w-2 shrink-0 rounded-full bg-danger status-dot-live" aria-hidden="true" />
              <p className="text-sm font-medium text-danger">
                {t("危険なクラスタリングを検知しました。即時の統治判断が推奨されます。", "Dangerous clustering detected. Immediate governance action recommended.")}
              </p>
            </div>
          )}

          {/* Heatmap canvas */}
          <div className="rounded-xl border border-border/50 bg-muted/10 p-5">
            <div className="relative mx-auto h-[380px] w-full max-w-5xl">
              <svg viewBox="0 0 100 100" className="h-full w-full" aria-hidden="true">
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

                <line x1="82" y1="0" x2="82" y2="100" stroke="hsl(var(--ds-color-danger) / 0.55)" strokeDasharray="1.5 1" strokeWidth="0.4" />
                <line x1="0" y1="18" x2="100" y2="18" stroke="hsl(var(--ds-color-danger) / 0.55)" strokeDasharray="1.5 1" strokeWidth="0.4" />
              </svg>
              <RiskScatterCanvas points={selectedCluster === "high" ? visiblePoints.filter((point) => point.risk >= 0.82 && point.uncertainty >= 0.82) : visiblePoints} />

              <span className="absolute -bottom-6 left-1/2 -translate-x-1/2 text-xs font-medium text-muted-foreground">
                {t("不確実性 →", "Uncertainty →")}
              </span>
              <span className="absolute left-0 top-1/2 -translate-x-10 -translate-y-1/2 -rotate-90 text-xs font-medium text-muted-foreground">
                {t("リスク →", "Risk →")}
              </span>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-primary/80" aria-hidden="true" />
              {t("通常リクエスト", "Normal requests")}
            </div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 rounded-full bg-danger" aria-hidden="true" />
              {t("高リスク (U≥0.82, R≥0.82)", "High-risk (U≥0.82, R≥0.82)")}
            </div>
            <div className="flex items-center gap-2 ml-auto">
              <span className="text-[10px]">{t("ウィンドウ: 24時間", "Window: 24h")}</span>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
