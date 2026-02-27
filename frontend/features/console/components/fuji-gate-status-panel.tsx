import { type DecideResponse } from "@veritas/types";
import { toFiniteNumber } from "../analytics/utils";

export function FujiGateStatusPanel({ result }: { result: DecideResponse | null }): JSX.Element {
  if (!result) {
    return (
      <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
        <h3 className="text-sm font-semibold text-foreground">FUJI Gate Status</h3>
        <p className="mt-2 text-xs text-muted-foreground">No evaluation yet.</p>
      </section>
    );
  }

  const gate = (result.gate ?? {}) as Record<string, unknown>;
  const status = typeof gate.decision_status === "string" ? gate.decision_status : "unknown";
  const risk = toFiniteNumber(gate.risk);
  const statusTone =
    status === "allow"
      ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-200"
      : status === "modify"
        ? "border-amber-500/40 bg-amber-500/10 text-amber-200"
        : "border-red-500/40 bg-red-500/10 text-red-200";

  return (
    <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
      <h3 className="text-sm font-semibold text-foreground">FUJI Gate Status</h3>
      <p className={`mt-2 inline-flex rounded-full border px-2 py-1 text-xs font-semibold ${statusTone}`}>
        {status.toUpperCase()}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">Risk score: {risk !== null ? risk.toFixed(3) : "n/a"}</p>
      <p className="mt-1 text-xs text-muted-foreground">Rejection reason: {result.rejection_reason ?? "none"}</p>
    </section>
  );
}
