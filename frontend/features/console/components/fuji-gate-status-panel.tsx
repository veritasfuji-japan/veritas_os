import { type DecideResponse } from "@veritas/types";
import { toFujiGateDetailView } from "../adapters/decision-view";

export function FujiGateStatusPanel({ result }: { result: DecideResponse | null }): JSX.Element {
  const view = toFujiGateDetailView(result);

  const decisionColor =
    view.decision === "deny"
      ? "text-destructive"
      : view.decision === "hold" || view.decision === "modify"
        ? "text-amber-400"
        : view.decision === "allow"
          ? "text-emerald-400"
          : "text-foreground";

  return (
    <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
      <h3 className="text-sm font-semibold text-foreground">FUJI Gate</h3>
      {!result && (
        <p className="mt-2 text-xs text-muted-foreground">Run a decision to inspect FUJI rules, severity, and remediation hints.</p>
      )}
      <div className="mt-2 grid gap-2 text-xs md:grid-cols-5">
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">allow / modify / rejected</p>
          <p className={`font-semibold ${decisionColor}`}>{view.decision}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">rule hit</p>
          <p className="font-semibold text-foreground">{view.ruleHit}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">severity</p>
          <p className="font-semibold text-foreground">{view.severity}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">remediation hint</p>
          <p className="font-semibold text-foreground">{view.remediationHint}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">risky text fragment preview</p>
          <p className="font-semibold text-foreground">{view.riskyFragmentPreview}</p>
        </div>
      </div>

      {/* Risk score and reasons drilldown */}
      {result && (view.riskScore !== null || view.reasons.length > 0 || view.violations.length > 0) && (
        <details className="mt-3" data-testid="fuji-drilldown">
          <summary className="cursor-pointer text-xs font-medium text-muted-foreground hover:text-foreground">
            Details: risk score, reasons &amp; violations ({view.violations.length})
          </summary>
          <div className="mt-2 space-y-2 text-xs">
            {view.riskScore !== null && (
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">Risk score:</span>
                <div className="relative h-2 w-20 rounded-full bg-muted/30">
                  <div
                    className={`absolute inset-y-0 left-0 rounded-full ${view.riskScore >= 0.7 ? "bg-red-500" : view.riskScore >= 0.4 ? "bg-amber-500" : "bg-emerald-500"}`}
                    style={{ width: `${Math.round(view.riskScore * 100)}%` }}
                  />
                </div>
                <span className="font-mono text-foreground">{(view.riskScore * 100).toFixed(0)}%</span>
              </div>
            )}
            {view.reasons.length > 0 && (
              <div>
                <p className="text-muted-foreground">Reasons:</p>
                <ul className="ml-3 list-disc text-foreground">
                  {view.reasons.map((reason, i) => (
                    <li key={`reason-${i}`}>{reason}</li>
                  ))}
                </ul>
              </div>
            )}
            {view.violations.length > 0 && (
              <div className="overflow-x-auto">
                <p className="text-muted-foreground">Violations:</p>
                <table className="mt-1 min-w-full text-xs">
                  <thead className="text-left text-muted-foreground">
                    <tr>
                      <th className="px-2 py-1">Rule</th>
                      <th className="px-2 py-1">Detail</th>
                      <th className="px-2 py-1">Severity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.violations.map((v, i) => (
                      <tr key={`violation-${i}`} className="border-t border-border/50">
                        <td className="px-2 py-1 font-mono">{v.rule}</td>
                        <td className="px-2 py-1">{v.detail}</td>
                        <td className="px-2 py-1">{v.severity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </details>
      )}
    </section>
  );
}
