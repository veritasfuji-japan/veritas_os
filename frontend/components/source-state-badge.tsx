import { type SourceState } from "../lib/source-state-utils";

interface SourceStateBadgeProps {
  state: SourceState;
  reason?: string;
  compact?: boolean;
  className?: string;
}

export function SourceStateBadge({ state, reason, compact = false, className }: SourceStateBadgeProps): JSX.Element {
  const sizeClass = compact ? "px-1 py-0.5 text-[9px]" : "px-1.5 py-0.5 text-[10px]";
  const accessibleLabel = reason ? `source state: ${state} (${reason})` : `source state: ${state}`;
  return (
    <span
      className={[
        "inline-flex rounded border border-border/60 bg-muted uppercase tracking-wide",
        sizeClass,
        className ?? "",
      ].join(" ").trim()}
      aria-label={accessibleLabel}
      title={reason ? `reason: ${reason}` : undefined}
    >
      {state}
    </span>
  );
}
