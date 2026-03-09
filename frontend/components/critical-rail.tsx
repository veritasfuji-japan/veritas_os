import { type CriticalRailMetric } from "./dashboard-types";

interface CriticalRailProps {
  items: CriticalRailMetric[];
}

const SEVERITY_STYLE = {
  healthy: "text-success border-success/40",
  degraded: "text-warning border-warning/40",
  critical: "text-danger border-danger/40",
};

export function CriticalRail({ items }: CriticalRailProps): JSX.Element {
  return (
    <section aria-label="critical rail" className="rounded-xl border border-danger/30 bg-danger/8 p-4">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-danger">Critical Rail</p>
      <div className="grid gap-2 md:grid-cols-5">
        {items.map((item) => (
          <a key={item.key} href={item.href} className="rounded-lg border border-border/60 bg-background/70 p-3 text-xs">
            <div className="mb-1 flex items-center justify-between">
              <p className="font-semibold text-foreground">{item.label}</p>
              <span className={["rounded border px-1.5 py-0.5 text-[10px]", SEVERITY_STYLE[item.severity]].join(" ")}>
                {item.severity}
              </span>
            </div>
            <p className="text-sm font-semibold">{item.currentValue}</p>
            <p className="text-muted-foreground">vs baseline: {item.baselineDelta}</p>
            <p className="mt-1 text-[10px] text-muted-foreground">Owner: {item.owner}</p>
            <p className="text-[10px] text-muted-foreground">Last updated: {item.lastUpdated}</p>
            <p className="text-[10px] text-muted-foreground">Open incidents: {item.openIncidents}</p>
          </a>
        ))}
      </div>
    </section>
  );
}
