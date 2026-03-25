import { type DecideResponse } from "@veritas/types";
import { toDecisionResultView } from "../adapters/decision-view";

interface DecisionResultPanelProps {
  result: DecideResponse;
}

/** Renders a horizontal score bar (0-1 range). */
function ScoreBar({ score, label }: { score: number | null; label: string }): JSX.Element {
  if (score === null) {
    return (
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">{label}:</span>
        <span className="text-muted-foreground">-</span>
      </div>
    );
  }
  const pct = Math.round(score * 100);
  const color = pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-red-500";
  return (
    <div className="flex items-center gap-2">
      <span className="text-muted-foreground">{label}:</span>
      <div className="relative h-2 w-20 rounded-full bg-muted/30">
        <div className={`absolute inset-y-0 left-0 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-foreground">{pct}%</span>
    </div>
  );
}

/**
 * Structured decision result panel for operator review.
 *
 * Displays chosen option alongside alternatives in a comparison-friendly
 * layout with value scores and rejection reasons.
 */
export function DecisionResultPanel({ result }: DecisionResultPanelProps): JSX.Element {
  const view = toDecisionResultView(result);

  return (
    <div className="space-y-3">
      {/* Chosen vs Alternatives comparison table */}
      {view.alternatives.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border bg-background/60">
          <table className="min-w-full text-xs" aria-label="chosen vs alternatives comparison">
            <thead className="border-b border-border/70 text-left text-muted-foreground">
              <tr>
                <th className="px-2 py-1.5">Option</th>
                <th className="px-2 py-1.5">Summary</th>
                <th className="px-2 py-1.5">Value Score</th>
                <th className="px-2 py-1.5">Trade-off / Weakness</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-primary/20 bg-primary/5">
                <td className="px-2 py-1.5">
                  <span className="inline-block rounded bg-primary/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-primary">Chosen</span>
                </td>
                <td className="px-2 py-1.5 font-medium text-foreground">{view.chosen.finalDecision}</td>
                <td className="px-2 py-1.5"><ScoreBar score={view.chosen.valueScore} label="value" /></td>
                <td className="px-2 py-1.5 text-muted-foreground">{view.chosen.whyChosen}</td>
              </tr>
              {view.alternatives.map((alt, index) => (
                <tr key={`${alt.optionSummary}-${index}`} className="border-b border-border/50">
                  <td className="px-2 py-1.5">
                    <span className="text-[10px] text-muted-foreground">Alt {index + 1}</span>
                  </td>
                  <td className="px-2 py-1.5 text-foreground">{alt.optionSummary}</td>
                  <td className="px-2 py-1.5"><ScoreBar score={alt.valueScore} label="value" /></td>
                  <td className="px-2 py-1.5 text-muted-foreground">
                    {alt.tradeOff !== "n/a" ? alt.tradeOff : alt.relativeWeakness}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-3">
        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">Chosen</h3>
          <p><span className="text-muted-foreground">final decision:</span> {view.chosen.finalDecision}</p>
          <p><span className="text-muted-foreground">why chosen:</span> {view.chosen.whyChosen}</p>
          <p><span className="text-muted-foreground">supporting evidence summary:</span> {view.chosen.supportingEvidenceSummary}</p>
          <p><span className="text-muted-foreground">value rationale:</span> {view.chosen.valueRationale}</p>
          <ScoreBar score={view.chosen.valueScore} label="value score" />
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">Alternatives</h3>
          {view.alternatives.length === 0 ? (
            <p className="text-muted-foreground">No alternatives provided.</p>
          ) : (
            view.alternatives.map((item, index) => (
              <div key={`${item.optionSummary}-${index}`} className="rounded border border-border/70 bg-background/70 p-2">
                <p><span className="text-muted-foreground">option summary:</span> {item.optionSummary}</p>
                <p><span className="text-muted-foreground">trade-off:</span> {item.tradeOff}</p>
                <p><span className="text-muted-foreground">relative weakness:</span> {item.relativeWeakness}</p>
                <ScoreBar score={item.valueScore} label="value score" />
              </div>
            ))
          )}
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">Rejected reasons</h3>
          <p><span className="text-muted-foreground">FUJI block:</span> {view.rejectedReasons.fujiBlock}</p>
          <p><span className="text-muted-foreground">weak evidence:</span> {view.rejectedReasons.weakEvidence}</p>
          <p><span className="text-muted-foreground">poor debate outcome:</span> {view.rejectedReasons.poorDebateOutcome}</p>
          <p><span className="text-muted-foreground">value conflict:</span> {view.rejectedReasons.valueConflict}</p>
        </section>
      </div>
    </div>
  );
}
