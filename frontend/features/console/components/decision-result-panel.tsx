import { type DecideResponse } from "@veritas/types";
import { toDecisionResultView } from "../adapters/decision-view";

interface DecisionResultPanelProps {
  result: DecideResponse;
}

/**
 * Structured decision result panel for operator review.
 */
export function DecisionResultPanel({ result }: DecisionResultPanelProps): JSX.Element {
  const view = toDecisionResultView(result);

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
        <h3 className="text-sm font-semibold text-foreground">Chosen</h3>
        <p><span className="text-muted-foreground">final decision:</span> {view.chosen.finalDecision}</p>
        <p><span className="text-muted-foreground">why chosen:</span> {view.chosen.whyChosen}</p>
        <p><span className="text-muted-foreground">supporting evidence summary:</span> {view.chosen.supportingEvidenceSummary}</p>
        <p><span className="text-muted-foreground">value rationale:</span> {view.chosen.valueRationale}</p>
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
  );
}
