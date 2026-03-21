"use client";

interface SuccessBannerProps {
  message: string;
  className?: string;
}

export function SuccessBanner({ message, className }: SuccessBannerProps): JSX.Element {
  return (
    <div
      role="status"
      className={`rounded-lg border border-success/40 px-3 py-2 text-sm text-success${className ? ` ${className}` : ""}`}
    >
      {message}
    </div>
  );
}
