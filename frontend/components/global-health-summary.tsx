import { Card } from "@veritas/design-system";
import { type GlobalHealthSummaryModel } from "./dashboard-types";

interface GlobalHealthSummaryProps {
  summary: GlobalHealthSummaryModel;
}

const BAND_STYLE = {
  healthy: "text-success",
  degraded: "text-warning",
  critical: "text-danger",
};

export function GlobalHealthSummary({ summary }: GlobalHealthSummaryProps): JSX.Element {
  return (
    <Card
      title="Global Health Summary"
      titleSize="md"
      variant="glass"
      className="border-border/60"
      description="healthy / degraded / critical の3区分で司令塔の現状を要約"
    >
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-2 text-xs">
          <p>
            Current band:
            {" "}
            <span className={["font-semibold", BAND_STYLE[summary.band]].join(" ")}>{summary.band}</span>
          </p>
          <p>24h incidents: {summary.incidents24h}</p>
          <div>
            <p className="font-semibold">今日の主要変化</p>
            <ul className="list-disc pl-4 text-muted-foreground">
              {summary.todayChanges.map((change) => (
                <li key={change}>{change}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className="space-y-2 text-xs text-muted-foreground">
          <p>Policy drift: {summary.policyDrift}</p>
          <p>Trust degradation: {summary.trustDegradation}</p>
          <p>Decision anomalies: {summary.decisionAnomalies}</p>
        </div>
      </div>
    </Card>
  );
}
