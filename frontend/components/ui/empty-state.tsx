"use client";

interface EmptyStateProps {
  title: string;
  description: string;
  icon?: JSX.Element;
  action?: JSX.Element;
  className?: string;
}

export function EmptyState({ title, description, icon, action, className }: EmptyStateProps): JSX.Element {
  return (
    <div className={`flex flex-col items-center gap-3 py-8 text-center${className ? ` ${className}` : ""}`}>
      {icon ? (
        <div className="rounded-full border-2 border-dashed border-muted p-4">
          {icon}
        </div>
      ) : null}
      <div>
        <p className="text-sm font-semibold">{title}</p>
        <p className="mt-1 text-xs text-muted-foreground">{description}</p>
      </div>
      {action ?? null}
    </div>
  );
}
