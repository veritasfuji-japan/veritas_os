"use client";

interface StaleBannerProps {
  message: string;
  onRefresh?: () => void;
  refreshLabel?: string;
  className?: string;
}

export function StaleBanner({ message, onRefresh, refreshLabel, className }: StaleBannerProps): JSX.Element {
  return (
    <div
      role="status"
      className={`rounded-lg border border-warning/20 bg-warning/5 px-3 py-2 text-sm text-warning${className ? ` ${className}` : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span>{message}</span>
        {onRefresh ? (
          <button
            type="button"
            onClick={onRefresh}
            className="shrink-0 rounded border border-warning/30 px-2 py-0.5 text-xs font-medium hover:bg-warning/10 transition-colors"
          >
            {refreshLabel ?? "Refresh"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
