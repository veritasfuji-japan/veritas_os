import { Card } from "@veritas/design-system";
import { type DecideResponse } from "@veritas/types";
import { buildPipelineStepViews } from "../analytics/pipeline";

export function StepExpansionPanel({ result }: { result: DecideResponse | null }): JSX.Element | null {
  if (!result) {
    return null;
  }

  return (
    <Card title="Step Expansion" className="bg-background/75">
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
