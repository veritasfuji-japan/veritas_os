import { useId } from "react";
import { renderValue } from "../analytics/utils";

interface SectionProps {
  title: string;
  value: unknown;
}

export function ResultSection({ title, value }: SectionProps): JSX.Element {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="space-y-2">
      <h3 className="text-sm font-semibold text-foreground" id={titleId}>
        {title}
      </h3>
      <pre className="overflow-x-auto rounded-md border border-border bg-background/70 p-3 text-xs text-foreground">
        {renderValue(value)}
      </pre>
    </section>
  );
}
