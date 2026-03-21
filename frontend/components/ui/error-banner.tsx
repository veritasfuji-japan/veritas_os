"use client";

interface ErrorBannerProps {
  message: string;
  variant?: "danger" | "warning";
  className?: string;
  onRetry?: () => void;
  retryLabel?: string;
}

export function ErrorBanner({ message, variant = "danger", className, onRetry, retryLabel }: ErrorBannerProps): JSX.Element {
  const styles = variant === "danger"
    ? "border-danger/30 bg-danger/10 text-danger"
    : "border-warning/30 bg-warning/10 text-warning";

  return (
    <div
      role="alert"
      className={`rounded-lg border px-3 py-2 text-sm ${styles}${className ? ` ${className}` : ""}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span>{message}</span>
        {onRetry ? (
          <button
            type="button"
            onClick={onRetry}
            className="shrink-0 rounded border border-current/30 px-2 py-0.5 text-xs font-medium hover:bg-current/10 transition-colors"
          >
            {retryLabel ?? "Retry"}
          </button>
        ) : null}
      </div>
    </div>
  );
}
