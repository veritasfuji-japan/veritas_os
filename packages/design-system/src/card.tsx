import * as React from "react";
import { cn } from "./utils";

export function Card({
  title,
  className,
  children
}: {
  title: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <section className={cn("w-full rounded-lg border bg-background p-6 shadow-sm", className)}>
      <h1 className="text-xl font-semibold">{title}</h1>
      <div className="mt-3">{children}</div>
    </section>
  );
}
