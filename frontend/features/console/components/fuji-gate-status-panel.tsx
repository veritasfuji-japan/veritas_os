import { type DecideResponse } from "@veritas/types";
import { toFiniteNumber } from "../analytics/utils";

function toViolationEntries(result: DecideResponse): Array<{ key: string; value: unknown }> {
  const fuji = (result.fuji ?? {}) as Record<string, unknown>;
  const gate = (result.gate ?? {}) as Record<string, unknown>;

  return Object.entries({ ...fuji, ...gate }).filter(([, value]) => {
    if (typeof value === "boolean") {
      return value;
    }
    if (typeof value === "string") {
      const lower = value.toLowerCase();
      return ["deny", "reject", "fail", "violation"].some((token) => lower.includes(token));
    }
    if (typeof value === "number") {
      return value >= 0.7;
    }
    return false;
  }).map(([key, value]) => ({ key, value }));
}

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
  const violations = toViolationEntries(result);

  return (
    <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
      <h3 className="text-sm font-semibold text-foreground">FUJI Gate Violation Analysis</h3>
      <p className="mt-1 text-xs text-muted-foreground">Decision: {status.toUpperCase()} · Risk {risk?.toFixed(3) ?? "n/a"}</p>
      <p className="mt-1 text-xs text-muted-foreground">Rejection reason: {result.rejection_reason ?? "none"}</p>
      <div className="mt-3 space-y-2">
        {violations.length === 0 ? (
          <p className="rounded-md border border-success/30 bg-success/10 px-2 py-1 text-xs text-success">No active violations.</p>
        ) : (
          violations.map((item) => (
            <div key={item.key} className="rounded-md border border-danger/30 bg-danger/8 px-2 py-1.5 text-xs text-danger">
              <span className="font-semibold">{item.key}</span>: {String(item.value)}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
