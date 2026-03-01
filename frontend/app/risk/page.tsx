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

  const clusterStats = useMemo(() => {
    const highRiskPoints = points.filter(
      (point) => point.uncertainty >= ALERT_CLUSTER_THRESHOLD && point.risk >= ALERT_CLUSTER_THRESHOLD,
    );
    const ratio = points.length === 0 ? 0 : highRiskPoints.length / points.length;
    return {
      ratio,
      count: highRiskPoints.length,
      alert: highRiskPoints.length >= 15 || ratio >= 0.08,
    };
  }, [points]);

  return (
    <div className="space-y-6">
      <Card title="Risk Intelligence" className="border-border/70 bg-surface/85 p-1 shadow-sm">
        <p className="max-w-4xl text-sm leading-relaxed text-muted-foreground">
          {t("過去24時間の全リクエストを不確実性（横軸）と潜在的リスク（縦軸）でリアルタイム可視化します。危険なクラスタリングを検知するとアラートを表示し、予防的な統治判断を支援します。", "Visualize all requests from the last 24 hours in real time by uncertainty (x-axis) and potential risk (y-axis). When dangerous clustering is detected, alerts support proactive governance decisions.")}
        </p>
      </Card>

      <Card
        title="Real-time Risk Heatmap"
        className="border-border/70 bg-background/80 shadow-sm"
      >
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${
                  clusterStats.alert
                    ? "bg-destructive/15 text-destructive"
                    : "bg-primary/15 text-primary"
                }`}
              >
                {clusterStats.alert ? "Cluster Alert" : "Normal"}
              </span>
              <span className="text-muted-foreground">
                High-Risk Cluster: {clusterStats.count} / {points.length} (
                {(clusterStats.ratio * 100).toFixed(1)}%)
              </span>
            </div>
            <span className="text-xs text-muted-foreground" aria-live="polite">
              Last update: {new Date(now).toLocaleTimeString(language === "ja" ? "ja-JP" : "en-US", { hour12: false })}
            </span>
          </div>

          <div className="rounded-xl border border-border/70 bg-surface/40 p-4">
            <div className="relative mx-auto h-[360px] w-full max-w-5xl">
              <svg viewBox="0 0 100 100" className="h-full w-full" aria-hidden="true">
                <defs>
                  <linearGradient id="riskGradient" x1="0" y1="100" x2="100" y2="0">
                    <stop offset="0%" stopColor="hsl(var(--primary) / 0.18)" />
                    <stop offset="55%" stopColor="hsl(var(--warning) / 0.2)" />
                    <stop offset="100%" stopColor="hsl(var(--destructive) / 0.28)" />
                  </linearGradient>
                </defs>

                <rect x="0" y="0" width="100" height="100" fill="url(#riskGradient)" rx="2" />

                {[20, 40, 60, 80].map((line) => (
                  <g key={line}>
                    <line x1={line} y1={0} x2={line} y2={100} stroke="hsl(var(--border) / 0.6)" strokeWidth="0.3" />
                    <line x1={0} y1={line} x2={100} y2={line} stroke="hsl(var(--border) / 0.6)" strokeWidth="0.3" />
                  </g>
                ))}

                <line x1="82" y1="0" x2="82" y2="100" stroke="hsl(var(--destructive) / 0.6)" strokeDasharray="1 1" strokeWidth="0.4" />
                <line x1="0" y1="18" x2="100" y2="18" stroke="hsl(var(--destructive) / 0.6)" strokeDasharray="1 1" strokeWidth="0.4" />
              </svg>
              <RiskScatterCanvas points={points} />

              <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 text-xs text-muted-foreground">
                Uncertainty →
              </span>
              <span className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-8 -rotate-90 text-xs text-muted-foreground">
                Risk →
              </span>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
