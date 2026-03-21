"use client";

import Link from "next/link";
import { Card } from "@veritas/design-system";
import { useI18n } from "../../components/i18n-provider";
import { getCluster } from "./data-helpers";
import { useRiskStream } from "./hooks/useRiskStream";
import { RiskScatterPlot } from "./components/RiskScatterPlot";
import { InsightCards } from "./components/InsightCards";
import { TrendChart } from "./components/TrendChart";
import { FlaggedRequestsList } from "./components/FlaggedRequestsList";
import { DrilldownPanel } from "./components/DrilldownPanel";
import { WhyFlaggedPanel } from "./components/WhyFlaggedPanel";

/* ------------------------------------------------------------------ */
/*  Page component                                                     */
/* ------------------------------------------------------------------ */

export default function RiskIntelligencePage(): JSX.Element {
  const { t, language } = useI18n();
  const stream = useRiskStream();

  const uncertainCount = stream.visiblePoints.filter((p) => getCluster(p) === "uncertain").length;

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
          {/* Status metrics */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("ステータス", "Status")}</p>
              <p className={`mt-0.5 font-semibold ${stream.clusterStats.alert ? "text-danger" : "text-success"}`}>
                {stream.clusterStats.alert ? "Cluster Alert" : "Normal"}
              </p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("高リスク", "High-risk")}</p>
              <p className="mt-0.5 font-mono font-semibold text-foreground">{stream.clusterStats.count} / {stream.visiblePoints.length}</p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("クラスタ率", "Cluster rate")}</p>
              <p className="mt-0.5 font-mono font-semibold text-foreground">{(stream.clusterStats.ratio * 100).toFixed(1)}%</p>
            </div>
            <div className="rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{t("最終更新", "Updated")}</p>
              <p className="mt-0.5 font-mono text-[11px] font-semibold text-foreground" aria-live="polite">
                {new Date(stream.now).toLocaleTimeString(language === "ja" ? "ja-JP" : "en-US", { hour12: false })}
              </p>
            </div>
          </div>

          {/* Filter controls */}
          <div className="flex flex-wrap items-end gap-3 rounded-lg border border-border/50 bg-background/60 px-3 py-2.5 text-xs">
            <label className="space-y-1">
              <span className="text-muted-foreground">Time window</span>
              <select className="block rounded border border-border bg-background px-2 py-1" value={stream.timeWindowHours} onChange={(event) => stream.setTimeWindowHours(Number(event.target.value))}>
                <option value={1}>1h</option>
                <option value={6}>6h</option>
                <option value={12}>12h</option>
                <option value={24}>24h</option>
              </select>
            </label>
            <label className="space-y-1">
              <span className="text-muted-foreground">Cluster drilldown</span>
              <select className="block rounded border border-border bg-background px-2 py-1" value={stream.selectedCluster} onChange={(event) => stream.setSelectedCluster(event.target.value as "all" | "critical" | "risky" | "uncertain")}>
                <option value="all">all points</option>
                <option value="critical">critical cluster</option>
                <option value="risky">high risk only</option>
                <option value="uncertain">high uncertainty only</option>
              </select>
            </label>
          </div>

          {/* Scatter plot */}
          <RiskScatterPlot
            filteredPoints={stream.filteredPoints}
            selectedPointId={stream.selectedPointId}
            hoveredPointId={stream.hoveredPointId}
            hoveredPoint={stream.hoveredPoint}
            onSelectPoint={stream.setSelectedPointId}
            onHoverPoint={stream.setHoveredPointId}
          />

          {/* Insight cards */}
          <InsightCards
            clusterRatio={stream.clusterStats.ratio}
            clusterCount={stream.clusterStats.count}
            filteredPointsCount={stream.filteredPoints.length}
            unsafeBurst={stream.unsafeBurst}
            latestHighRisk={stream.latestHighRisk}
            uncertainCount={uncertainCount}
          />

          {/* Trend + Flagged requests */}
          <div className="grid gap-4 lg:grid-cols-2">
            <TrendChart
              trend={stream.trend}
              spikeDetected={stream.spikeDetected}
              unsafeBurst={stream.unsafeBurst}
              onSelectCluster={stream.setSelectedCluster}
            />
            <FlaggedRequestsList
              entries={stream.flaggedEntries}
              selectedPointId={stream.selectedPointId}
              onSelectPoint={stream.setSelectedPointId}
            />
          </div>

          {/* Drilldown + Why flagged */}
          <DrilldownPanel entry={stream.selectedEntry} />
          <WhyFlaggedPanel entry={stream.selectedEntry} />
        </div>
      </Card>
    </div>
  );
}
