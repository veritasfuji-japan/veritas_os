import { type DecideResponse } from "@veritas/types";
import { toDecisionResultView, toPublicDecisionSchemaView } from "../adapters/decision-view";

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
  const publicDecision = toPublicDecisionSchemaView(result);
  const missingEvidence = publicDecision.missingEvidence;
  const evidencePending = missingEvidence.length > 0;

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
        <section className="space-y-3 rounded-md border border-border bg-background/60 p-3 text-xs md:col-span-2">
          <header className="space-y-2">
            <h3 className="text-sm font-semibold text-foreground">Public decision output</h3>
            <p><span className="text-muted-foreground">gate_decision:</span> {publicDecision.gateDecision}</p>
            <p><span className="text-muted-foreground">gate meaning:</span> {publicDecision.gateDecisionLabel}</p>
            <p><span className="text-muted-foreground">business_decision:</span> {publicDecision.businessDecision}</p>
            <p><span className="text-muted-foreground">human_review_required:</span> {publicDecision.humanReviewRequired ? "true" : "false"}</p>
          </header>

          <div className="grid gap-3 md:grid-cols-2">
            <article className="space-y-2 rounded-md border border-amber-400/40 bg-amber-500/5 p-3">
              <h4 className="font-semibold text-foreground">不足証拠 / Missing evidence</h4>
              {evidencePending ? (
                <ul className="list-disc space-y-1 pl-4">
                  {missingEvidence.map((item) => (
                    <li key={item} className="font-mono text-[11px] text-foreground">{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">不足証拠はありません。</p>
              )}
              <p><span className="text-muted-foreground">required_evidence:</span> {publicDecision.requiredEvidence.length > 0 ? publicDecision.requiredEvidence.join(", ") : "none"}</p>
            </article>

            <article className="space-y-2 rounded-md border border-emerald-400/40 bg-emerald-500/5 p-3">
              <h4 className="font-semibold text-foreground">次に実行するアクション / Next action</h4>
              <p className="font-mono text-[11px] text-foreground">{publicDecision.nextAction}</p>
              <p className="text-muted-foreground">
                案件状態（business_decision）とは分離された実行ガイダンスです。
              </p>
            </article>
          </div>
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">Viewer focus</h3>
          <div className="space-y-2 rounded-md border border-border/70 bg-background/70 p-2">
            <p className="font-medium text-foreground">監査人向け</p>
            <p><span className="text-muted-foreground">判定:</span> {publicDecision.businessDecision}</p>
            <p><span className="text-muted-foreground">人手審査:</span> {publicDecision.humanReviewRequired ? "必須" : "不要"}</p>
          </div>
          <div className="space-y-2 rounded-md border border-border/70 bg-background/70 p-2">
            <p className="font-medium text-foreground">開発者向け</p>
            <p><span className="text-muted-foreground">active posture:</span> {publicDecision.activePosture ?? "n/a"}</p>
            <p><span className="text-muted-foreground">backend:</span> {publicDecision.backend ?? "n/a"}</p>
            <p><span className="text-muted-foreground">verify status:</span> {publicDecision.verifyStatus ?? "n/a"}</p>
          </div>
        </section>

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
