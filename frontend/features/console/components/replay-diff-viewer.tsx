import { type DecideResponse } from "@veritas/types";

interface ReplayDiffViewerProps {
  result: DecideResponse;
}

/** Classify per-field severity for audit visibility. */
function fieldSeverity(key: string): "critical" | "warning" | "info" {
  if (key === "decision" || key === "fuji") return "critical";
  if (key === "value_scores") return "warning";
  // Continuation runtime (shadow/observe) — warning-level because phase-1 is non-enforcing.
  if (key === "continuation_state" || key === "continuation_receipt") return "warning";
  return "info";
}

const severityStyles: Record<string, string> = {
  critical: "bg-destructive/10 border-l-2 border-destructive",
  warning: "bg-warning/10 border-l-2 border-warning",
  info: "",
};

const severityLabels: Record<string, string> = {
  critical: "CRITICAL",
  warning: "WARNING",
  info: "",
};

/** Render a value as a readable string, handling nested objects. */
function renderDiffValue(value: unknown): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

/** Short summary label for a value: "{N keys}" for objects, rendered string otherwise. */
function valueSummary(value: unknown): string {
  if (typeof value === "object" && value !== null) {
    return `{${Object.keys(value as Record<string, unknown>).length} keys}`;
  }
  return renderDiffValue(value);
}
function isExpandable(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value !== "object") return false;
  return Object.keys(value as Record<string, unknown>).length > 0;
}

export function ReplayDiffViewer({ result }: ReplayDiffViewerProps): JSX.Element {
  const previousChosen = (result.extras?.replay_previous_chosen ?? {}) as Record<string, unknown>;
  const currentChosen = (result.chosen ?? {}) as Record<string, unknown>;

  const keys = Array.from(new Set([...Object.keys(previousChosen), ...Object.keys(currentChosen)]));

  // Determine overall divergence level for the header badge.
  const changedKeys = keys.filter(
    (k) => JSON.stringify(previousChosen[k]) !== JSON.stringify(currentChosen[k]),
  );
  const unchangedKeys = keys.filter((k) => !changedKeys.includes(k));
  const severities = changedKeys.map(fieldSeverity);
  const divergenceLevel = severities.includes("critical")
    ? "critical_divergence"
    : severities.length > 0
      ? "acceptable_divergence"
      : "no_divergence";

  const divergenceBadge: Record<string, { label: string; className: string }> = {
    critical_divergence: { label: "Critical Divergence", className: "text-destructive font-semibold" },
    acceptable_divergence: { label: "Acceptable Divergence", className: "text-warning font-semibold" },
    no_divergence: { label: "No Divergence", className: "text-muted-foreground" },
  };

  const badge = divergenceBadge[divergenceLevel] ?? divergenceBadge.no_divergence;

  // Build a plain-text change summary for quick scanning.
  const changeSummary = changedKeys.length === 0
    ? null
    : `${changedKeys.length} field(s) changed: ${changedKeys.join(", ")}`;
  const safetySensitiveChanged = changedKeys.filter((key) => fieldSeverity(key) === "critical");
  const orderedKeys = [...changedKeys, ...unchangedKeys];

  return (
    <section className="space-y-2" aria-label="replay diff viewer">
      <div className="flex items-center gap-2">
        <h3 className="text-sm font-semibold text-foreground">Replay diff viewer</h3>
        {keys.length > 0 && (
          <span className={`text-xs ${badge.className}`} data-testid="divergence-badge">
            {badge.label}
          </span>
        )}
      </div>
      {changeSummary && (
        <p className="text-xs text-muted-foreground" data-testid="change-summary">{changeSummary}</p>
      )}
      {safetySensitiveChanged.length > 0 && (
        <p className="rounded border border-destructive/40 bg-destructive/10 px-2 py-1 text-xs text-destructive" data-testid="safety-sensitive-warning">
          Safety-sensitive drift detected: {safetySensitiveChanged.join(", ")}. Re-approval is required before marking this run safe.
        </p>
      )}
      {keys.length === 0 ? (
        <p className="text-xs text-muted-foreground">No replay baseline is available.</p>
      ) : (
        <div className="overflow-auto rounded-md border border-border bg-background/70">
          <table className="min-w-full text-xs">
            <thead className="border-b border-border/70 text-left text-muted-foreground">
              <tr>
                <th className="px-2 py-1">Field</th>
                <th className="px-2 py-1">Previous</th>
                <th className="px-2 py-1">Current</th>
                <th className="px-2 py-1">Severity</th>
              </tr>
            </thead>
            <tbody>
              {orderedKeys.map((key) => {
                const previous = previousChosen[key];
                const current = currentChosen[key];
                const changed = JSON.stringify(previous) !== JSON.stringify(current);
                const severity = changed ? fieldSeverity(key) : "info";
                const rowClass = changed ? severityStyles[severity] || "bg-warning/10" : "";
                const needsExpand = isExpandable(previous) || isExpandable(current);
                return (
                  <tr key={key} className={rowClass}>
                    <td className="px-2 py-1 font-mono">{key}</td>
                    <td className="px-2 py-1">
                      {needsExpand ? (
                        <details>
                          <summary className="cursor-pointer">{valueSummary(previous)}</summary>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[10px]">{renderDiffValue(previous)}</pre>
                        </details>
                      ) : (
                        renderDiffValue(previous)
                      )}
                    </td>
                    <td className="px-2 py-1">
                      {needsExpand ? (
                        <details>
                          <summary className="cursor-pointer">{valueSummary(current)}</summary>
                          <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap text-[10px]">{renderDiffValue(current)}</pre>
                        </details>
                      ) : (
                        renderDiffValue(current)
                      )}
                    </td>
                    <td className="px-2 py-1 text-center">
                      {changed && severityLabels[severity] ? (
                        <span className="rounded px-1 text-[10px] font-bold uppercase">{severityLabels[severity]}</span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
