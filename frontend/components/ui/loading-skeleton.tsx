"use client";

interface LoadingSkeletonProps {
  lines?: number;
  className?: string;
}

export function LoadingSkeleton({ lines = 3, className }: LoadingSkeletonProps): JSX.Element {
  const skeletonLines = Array.from({ length: lines }, (_, index) => {
    const lineNumber = index + 1;
    return {
      key: `skeleton-line-${lineNumber}`,
      widthPercent: 75 + Math.sin(index) * 20
    };
  });

  return (
    <div
      role="status"
      aria-label="Loading"
      className={`animate-pulse space-y-2${className ? ` ${className}` : ""}`}
    >
      {skeletonLines.map((line) => (
        <div
          key={line.key}
          className="h-3 rounded bg-muted/40"
          style={{ width: `${line.widthPercent}%` }}
        />
      ))}
      <span className="sr-only">Loading...</span>
    </div>
  );
}
