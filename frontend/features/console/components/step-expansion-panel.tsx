import { Card } from "@veritas/design-system";
import { type DecideResponse } from "@veritas/types";
import { buildPipelineStepViews } from "../analytics/pipeline";

function readStageMetrics(result: DecideResponse): Array<{ stage: string; latencyMs: number; health: string }> {
  const metrics = (result.extras?.stage_metrics ?? {}) as Record<string, unknown>;
  return Object.entries(metrics).flatMap(([stage, raw]) => {
    if (typeof raw !== "object" || raw === null) {
      return [];
    }
    const row = raw as Record<string, unknown>;
    const latencyMs = typeof row.latency_ms === "number" ? row.latency_ms : 0;
    const health = typeof row.health === "string" ? row.health : "unknown";
    return [{ stage, latencyMs, health }];
  });
}

export function StepExpansionPanel({ result }: { result: DecideResponse | null }): JSX.Element | null {
  if (!result) {
    return null;
  }

  const metrics = readStageMetrics(result);

  return (
    <Card title="Stage Drilldown" className="bg-background/75">
      {metrics.length > 0 && (
        <div className="mb-3 grid gap-2 md:grid-cols-3">
          {metrics.map((item) => (
            <div key={item.stage} className="rounded-md border border-border bg-background/70 p-2 text-xs">
              <p className="font-semibold text-foreground">{item.stage}</p>
              <p className="font-mono text-muted-foreground">latency {item.latencyMs.toFixed(0)} ms</p>
              <p className={item.health === "healthy" ? "text-success" : item.health === "warning" ? "text-warning" : "text-danger"}>{item.health}</p>
            </div>
          ))}
        </div>
      )}
      <div className="space-y-2">
        {buildPipelineStepViews(result).map((step) => (
          <details key={`${step.name}-${step.summary}`} className="rounded-md border border-border bg-background/60 p-2">
            <summary className="cursor-pointer text-sm font-medium text-foreground">
              {step.name} · {step.summary}
              <span className="ml-2 text-[11px] uppercase text-muted-foreground">{step.status}</span>
            </summary>
            <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-background/70 p-2 text-xs text-foreground">
              {step.detail}
            </pre>
          </details>
        ))}
      </div>
    </Card>
  );
}
