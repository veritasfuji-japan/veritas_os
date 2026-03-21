"use client";

interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
}

export function LoadingSkeleton({ lines = 3, className }: LoadingSkeletonProps): JSX.Element {
  return (
    <div
      role="status"
      aria-label="Loading"
      className={`animate-pulse space-y-2${className ? ` ${className}` : ""}`}
    >
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="h-3 rounded bg-muted/40"
          style={{ width: `${75 + Math.sin(i) * 20}%` }}
        />
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}
