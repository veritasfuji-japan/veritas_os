"use client";

interface SectionHeaderProps {
  title: string;
  description?: string;
  trailing?: JSX.Element;
  className?: string;
}

export function SectionHeader({ title, description, trailing, className }: SectionHeaderProps): JSX.Element {
  return (
    <div className={`flex items-start justify-between gap-3${className ? ` ${className}` : ""}`}>
      <div className="min-w-0">
        <p className="text-xs font-semibold">{title}</p>
        {description ? (
          <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>
        ) : null}
      </div>
      {trailing ?? null}
    </div>
  );
}
