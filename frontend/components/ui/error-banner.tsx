"use client";

interface ErrorBannerProps {
  message: string;
  variant?: "danger" | "warning";
  className?: string;
}

export function ErrorBanner({ message, variant = "danger", className }: ErrorBannerProps): JSX.Element {
  const styles = variant === "danger"
    ? "border-danger/30 bg-danger/10 text-danger"
    : "border-warning/30 bg-warning/10 text-warning";

  return (
    <div
      role="alert"
      className={`rounded-lg border px-3 py-2 text-sm ${styles}${className ? ` ${className}` : ""}`}
    >
      {message}
    </div>
  );
}
