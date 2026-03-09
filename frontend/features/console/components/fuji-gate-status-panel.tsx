import { type DecideResponse } from "@veritas/types";
import { toFujiGateView } from "../adapters/decision-view";

export function FujiGateStatusPanel({ result }: { result: DecideResponse | null }): JSX.Element {
  const view = toFujiGateView(result);

  return (
    <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
      <h3 className="text-sm font-semibold text-foreground">FUJI Gate</h3>
      {!result && (
        <p className="mt-2 text-xs text-muted-foreground">Run a decision to inspect FUJI rules, severity, and remediation hints.</p>
      )}
      <div className="mt-2 grid gap-2 text-xs md:grid-cols-5">
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">allow / modify / rejected</p>
          <p className="font-semibold text-foreground">{view.decision}</p>
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
    </section>
  );
}
