import { type DecideResponse } from "@veritas/types";

interface ReplayDiffViewerProps {
  result: DecideResponse;
}

export function ReplayDiffViewer({ result }: ReplayDiffViewerProps): JSX.Element {
  const previousChosen = (result.extras?.replay_previous_chosen ?? {}) as Record<string, unknown>;
  const currentChosen = (result.chosen ?? {}) as Record<string, unknown>;

  const keys = Array.from(new Set([...Object.keys(previousChosen), ...Object.keys(currentChosen)]));

  return (
    <section className="space-y-2" aria-label="replay diff viewer">
      <h3 className="text-sm font-semibold text-foreground">Replay diff viewer</h3>
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
              </tr>
            </thead>
            <tbody>
              {keys.map((key) => {
                const previous = previousChosen[key];
                const current = currentChosen[key];
                const changed = JSON.stringify(previous) !== JSON.stringify(current);
                return (
                  <tr key={key} className={changed ? "bg-warning/10" : ""}>
                    <td className="px-2 py-1 font-mono">{key}</td>
                    <td className="px-2 py-1">{String(previous ?? "-")}</td>
                    <td className="px-2 py-1">{String(current ?? "-")}</td>
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
