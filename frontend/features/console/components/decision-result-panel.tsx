import { type DecideResponse } from "@veritas/types";
import { useI18n } from "../../../components/i18n-provider";
import {
  toDecisionResultView,
  toEvidenceBundleDraft,
  toPublicDecisionSchemaView,
  toRuntimeStatusView,
} from "../adapters/decision-view";
import { type ConsoleViewerRole, type EvidenceBundleDraft } from "../types";

interface DecisionResultPanelProps {
  result: DecideResponse;
  viewerRole?: ConsoleViewerRole;
  onGenerateBundle?: (bundle: EvidenceBundleDraft) => void;
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

function downloadEvidenceBundle(bundle: EvidenceBundleDraft): void {
  const payload = JSON.stringify(bundle, null, 2);
  const blob = new Blob([payload], { type: "application/json" });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `evidence-bundle-${bundle.requestId}.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

/**
 * Structured decision result panel for operator review.
 *
 * Displays chosen option alongside alternatives in a comparison-friendly
 * layout with value scores and rejection reasons.
 */
export function DecisionResultPanel({
  result,
  viewerRole = "operator",
  onGenerateBundle,
}: DecisionResultPanelProps): JSX.Element {
  const { tk } = useI18n();
  const view = toDecisionResultView(result);
  const publicDecision = toPublicDecisionSchemaView(result);
  const runtimeStatus = toRuntimeStatusView(result);
  const missingEvidence = publicDecision.missingEvidence;
  const evidencePending = missingEvidence.length > 0;

  const bundleHandler = () => {
    const bundleDraft = toEvidenceBundleDraft(result);
    if (onGenerateBundle) {
      onGenerateBundle(bundleDraft);
      return;
    }
    downloadEvidenceBundle(bundleDraft);
  };

  return (
    <div className="space-y-3">
      {view.alternatives.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-border bg-background/60">
          <table className="min-w-full text-xs" aria-label={tk("decisionPanelComparisonAriaLabel")}>
            <thead className="border-b border-border/70 text-left text-muted-foreground">
              <tr>
                <th className="px-2 py-1.5">{tk("decisionPanelOption")}</th>
                <th className="px-2 py-1.5">{tk("decisionPanelSummary")}</th>
                <th className="px-2 py-1.5">{tk("decisionPanelValueScore")}</th>
                <th className="px-2 py-1.5">{tk("decisionPanelTradeoff")}</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-primary/20 bg-primary/5">
                <td className="px-2 py-1.5">
                  <span className="inline-block rounded bg-primary/20 px-1.5 py-0.5 text-[10px] font-bold uppercase text-primary">
                    {tk("decisionPanelChosenBadge")}
                  </span>
                </td>
                <td className="px-2 py-1.5 font-medium text-foreground">{view.chosen.finalDecision}</td>
                <td className="px-2 py-1.5"><ScoreBar score={view.chosen.valueScore} label={tk("decisionPanelValueScore")} /></td>
                <td className="px-2 py-1.5 text-muted-foreground">{view.chosen.whyChosen}</td>
              </tr>
              {view.alternatives.map((alt, index) => (
                <tr key={`${alt.optionSummary}-${index}`} className="border-b border-border/50">
                  <td className="px-2 py-1.5">
                    <span className="text-[10px] text-muted-foreground">{tk("decisionPanelAlternativeLabel")} {index + 1}</span>
                  </td>
                  <td className="px-2 py-1.5 text-foreground">{alt.optionSummary}</td>
                  <td className="px-2 py-1.5"><ScoreBar score={alt.valueScore} label={tk("decisionPanelValueScore")} /></td>
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
            <h3 className="text-sm font-semibold text-foreground">{tk("decisionPanelPublicDecisionOutput")}</h3>
            <p><span className="text-muted-foreground">{tk("decisionPanelGateDecision")}:</span> {publicDecision.gateDecision}</p>
            <p><span className="text-muted-foreground">{tk("decisionPanelGateMeaning")}:</span> {publicDecision.gateDecisionLabel}</p>
            <p><span className="text-muted-foreground">{tk("decisionPanelBusinessDecision")}:</span> {publicDecision.businessDecision}</p>
            <p><span className="text-muted-foreground">{tk("decisionPanelHumanReviewRequired")}:</span> {publicDecision.humanReviewRequired ? "true" : "false"}</p>
          </header>

          <div className="grid gap-3 md:grid-cols-2">
            <article className="space-y-2 rounded-md border border-amber-400/40 bg-amber-500/5 p-3">
              <h4 className="font-semibold text-foreground">{tk("decisionPanelMissingEvidence")}</h4>
              {evidencePending ? (
                <ul className="list-disc space-y-1 pl-4">
                  {missingEvidence.map((item) => (
                    <li key={item} className="font-mono text-[11px] text-foreground">{item}</li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground">{tk("decisionPanelNoMissingEvidence")}</p>
              )}
              <p><span className="text-muted-foreground">{tk("decisionPanelRequiredEvidence")}:</span> {publicDecision.requiredEvidence.length > 0 ? publicDecision.requiredEvidence.join(", ") : tk("decisionPanelNone")}</p>
            </article>

            <article className="space-y-2 rounded-md border border-emerald-400/40 bg-emerald-500/5 p-3">
              <h4 className="font-semibold text-foreground">{tk("decisionPanelNextAction")}</h4>
              <p className="font-mono text-[11px] text-foreground">{publicDecision.nextAction}</p>
              <p className="text-muted-foreground">{tk("decisionPanelNextActionHint")}</p>
            </article>
          </div>
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">{tk("decisionPanelViewerFocus")}</h3>
          {viewerRole === "auditor" ? (
            <div className="space-y-2 rounded-md border border-border/70 bg-background/70 p-2">
              <p className="font-medium text-foreground">{tk("decisionPanelRoleAuditor")}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelDecision")}:</span> {publicDecision.businessDecision}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelHumanReview")}:</span> {publicDecision.humanReviewRequired ? tk("decisionPanelRequired") : tk("decisionPanelNotRequired")}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelRequiredEvidence")}:</span> {publicDecision.requiredEvidence.length}</p>
            </div>
          ) : null}
          {viewerRole === "operator" ? (
            <div className="space-y-2 rounded-md border border-border/70 bg-background/70 p-2">
              <p className="font-medium text-foreground">{tk("decisionPanelRoleOperator")}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelNextAction")}:</span> {publicDecision.nextAction}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelMissingEvidence")}:</span> {missingEvidence.length}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelGateDecision")}:</span> {publicDecision.gateDecision}</p>
            </div>
          ) : null}
          {viewerRole === "developer" ? (
            <div className="space-y-2 rounded-md border border-border/70 bg-background/70 p-2">
              <p className="font-medium text-foreground">{tk("decisionPanelRoleDeveloper")}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelActivePosture")}:</span> {runtimeStatus.activePosture}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelBackend")}:</span> {runtimeStatus.backend}</p>
              <p><span className="text-muted-foreground">{tk("decisionPanelVerifyStatus")}:</span> {runtimeStatus.verifyStatus}</p>
            </div>
          ) : null}

          <div className="rounded-md border border-border/70 bg-background/70 p-2">
            <p className="font-medium text-foreground">{tk("decisionPanelBundleTitle")}</p>
            <p className="text-muted-foreground">{tk("decisionPanelBundleHint")}</p>
            <button type="button" className="mt-2 rounded-md border border-border px-2 py-1 text-xs" onClick={bundleHandler}>
              {tk("decisionPanelBundleButton")}
            </button>
          </div>
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">{tk("decisionPanelChosenTitle")}</h3>
          <p><span className="text-muted-foreground">{tk("decisionPanelFinalDecision")}:</span> {view.chosen.finalDecision}</p>
          <p><span className="text-muted-foreground">{tk("decisionPanelWhyChosen")}:</span> {view.chosen.whyChosen}</p>
          <p><span className="text-muted-foreground">{tk("decisionPanelSupportingEvidenceSummary")}:</span> {view.chosen.supportingEvidenceSummary}</p>
          <p><span className="text-muted-foreground">{tk("decisionPanelValueRationale")}:</span> {view.chosen.valueRationale}</p>
          <ScoreBar score={view.chosen.valueScore} label={tk("decisionPanelValueScore")} />
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">{tk("decisionPanelAlternativesTitle")}</h3>
          {view.alternatives.length === 0 ? (
            <p className="text-muted-foreground">{tk("decisionPanelNoAlternatives")}</p>
          ) : (
            view.alternatives.map((item, index) => (
              <div key={`${item.optionSummary}-${index}`} className="rounded border border-border/70 bg-background/70 p-2">
                <p><span className="text-muted-foreground">{tk("decisionPanelOptionSummary")}:</span> {item.optionSummary}</p>
                <p><span className="text-muted-foreground">{tk("decisionPanelTradeOffField")}:</span> {item.tradeOff}</p>
                <p><span className="text-muted-foreground">{tk("decisionPanelRelativeWeakness")}:</span> {item.relativeWeakness}</p>
                <ScoreBar score={item.valueScore} label={tk("decisionPanelValueScore")} />
              </div>
            ))
          )}
        </section>

        <section className="space-y-2 rounded-md border border-border bg-background/60 p-3 text-xs">
          <h3 className="text-sm font-semibold text-foreground">{tk("decisionPanelRejectedReasonsTitle")}</h3>
          <p><span className="text-muted-foreground">{tk("decisionPanelFujiBlock")}:</span> {view.rejectedReasons.fujiBlock}</p>
          <p><span className="text-muted-foreground">{tk("decisionPanelWeakEvidence")}:</span> {view.rejectedReasons.weakEvidence}</p>
          <p><span className="text-muted-foreground">{tk("decisionPanelPoorDebateOutcome")}:</span> {view.rejectedReasons.poorDebateOutcome}</p>
          <p><span className="text-muted-foreground">{tk("decisionPanelValueConflict")}:</span> {view.rejectedReasons.valueConflict}</p>
        </section>
      </div>
    </div>
  );
}
