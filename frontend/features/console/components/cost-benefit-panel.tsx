import { useMemo } from "react";
import { type DecideResponse } from "@veritas/types";
import { buildCostBenefitAnalytics } from "../analytics/costBenefit";

export function CostBenefitPanel({ result }: { result: DecideResponse }): JSX.Element {
  const analytics = useMemo(() => buildCostBenefitAnalytics(result), [result]);

  return (
    <section
      className="space-y-3 rounded-md border border-border bg-background/60 p-3"
      aria-label="cost-benefit analytics"
    >
      <h3 className="text-sm font-semibold text-foreground">Cost-Benefit Analytics</h3>
      <p className="text-xs text-muted-foreground">
        Uncertainty reduction and token spend per heavy pipeline step.
      </p>
      {analytics.inferred ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 p-2 text-xs text-amber-200">
          推定表示: バックエンドの cost_benefit_analytics が未提供のため、レスポンス内容から概算しています。
        </p>
      ) : null}
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-xs text-foreground">
          <thead>
            <tr className="border-b border-border text-muted-foreground">
              <th className="px-2 py-1">Step</th>
              <th className="px-2 py-1">Executed</th>
              <th className="px-2 py-1">Δ Uncertainty</th>
              <th className="px-2 py-1">Token Cost</th>
            </tr>
          </thead>
          <tbody>
            {analytics.steps.map((step) => {
              const delta =
                step.uncertaintyBefore !== null && step.uncertaintyAfter !== null
                  ? step.uncertaintyBefore - step.uncertaintyAfter
                  : null;
              return (
                <tr key={step.name} className="border-b border-border/50">
                  <td className="px-2 py-1 font-medium">{step.name}</td>
                  <td className="px-2 py-1">{step.executed ? "Yes" : "No"}</td>
                  <td className="px-2 py-1">{delta !== null ? `${(delta * 100).toFixed(1)}%` : "-"}</td>
                  <td className="px-2 py-1">{step.tokenCost !== null ? step.tokenCost.toLocaleString() : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="rounded-md border border-border bg-background/80 p-2">
          <p className="text-[11px] text-muted-foreground">Total Token Cost</p>
          <p className="text-sm font-semibold text-foreground">{analytics.totalTokenCost.toLocaleString()}</p>
        </div>
        <div className="rounded-md border border-border bg-background/80 p-2">
          <p className="text-[11px] text-muted-foreground">Uncertainty Reduction</p>
          <p className="text-sm font-semibold text-foreground">
            {analytics.uncertaintyReduction !== null
              ? `${(analytics.uncertaintyReduction * 100).toFixed(1)}%`
              : "-"}
          </p>
        </div>
      </div>
    </section>
  );
}
