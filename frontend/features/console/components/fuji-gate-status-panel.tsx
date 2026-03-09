import { type DecideResponse } from "@veritas/types";

function readFujiField(data: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = data[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return "n/a";
}

export function FujiGateStatusPanel({ result }: { result: DecideResponse | null }): JSX.Element {
  if (!result) {
    return (
      <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
        <h3 className="text-sm font-semibold text-foreground">FUJI Gate Status</h3>
        <p className="mt-2 text-xs text-muted-foreground">Run a decision to inspect FUJI rules, severity, and remediation hints.</p>
      </section>
    );
  }

  const gate = (result.gate ?? {}) as Record<string, unknown>;
  const fuji = (result.fuji ?? {}) as Record<string, unknown>;
  const merged = { ...fuji, ...gate };

  const decision = readFujiField(merged, "decision_status", "status");
  const ruleHit = readFujiField(merged, "rule_hit", "rule", "policy_rule", "code");
  const severity = readFujiField(merged, "severity", "risk_level");
  const remediationHint = readFujiField(merged, "remediation_hint", "hint", "action");

  return (
    <section className="rounded-md border border-border bg-background/60 p-3" aria-label="fuji gate status">
      <h3 className="text-sm font-semibold text-foreground">FUJI Gate</h3>
      <div className="mt-2 grid gap-2 text-xs md:grid-cols-4">
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">decision</p>
          <p className="font-semibold text-foreground">{decision}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">rule hit</p>
          <p className="font-semibold text-foreground">{ruleHit}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">severity</p>
          <p className="font-semibold text-foreground">{severity}</p>
        </div>
        <div className="rounded border border-border/70 bg-background/70 p-2">
          <p className="text-muted-foreground">remediation hint</p>
          <p className="font-semibold text-foreground">{remediationHint}</p>
        </div>
      </div>
    </section>
  );
}
