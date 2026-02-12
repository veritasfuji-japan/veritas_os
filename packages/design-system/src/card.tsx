import * as React from "react";
import { cn } from "./utils";

interface CardProps {
  title: string;
  className?: string;
  children: React.ReactNode;
}

export function Card({ title, className, children }: CardProps): JSX.Element {
  const titleId = React.useId();

  return (
    <section
      aria-labelledby={titleId}
      className={cn("w-full rounded-lg border border-border bg-surface p-6 shadow-sm", className)}
    >
      <h2 className="text-xl font-semibold" id={titleId}>
        {title}
      </h2>
      <div className="mt-3 text-sm leading-relaxed">{children}</div>
    </section>
  );
}
