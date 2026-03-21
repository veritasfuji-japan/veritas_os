"use client";

import type { RiskPoint } from "../risk-types";
import { getCluster, pointFill } from "../data-helpers";

interface RiskScatterPlotProps {
  filteredPoints: RiskPoint[];
  selectedPointId: string | null;
  hoveredPointId: string | null;
  hoveredPoint: RiskPoint | null;
  onSelectPoint: (id: string) => void;
  onHoverPoint: (id: string | null) => void;
}

export function RiskScatterPlot({
  filteredPoints,
  selectedPointId,
  hoveredPointId,
  hoveredPoint,
  onSelectPoint,
  onHoverPoint,
}: RiskScatterPlotProps): JSX.Element {
  return (
    <div className="rounded-xl border border-border/50 bg-muted/10 p-5">
      <div className="relative mx-auto h-[380px] w-full max-w-5xl">
        <svg viewBox="0 0 100 100" className="h-full w-full" aria-label="Scatter plot of request uncertainty and risk from the last 24 hours" role="img">
          <defs>
            <linearGradient id="riskGradient" x1="0" y1="100" x2="100" y2="0">
              <stop offset="0%" stopColor="hsl(var(--ds-color-primary) / 0.12)" />
              <stop offset="50%" stopColor="hsl(var(--ds-color-warning) / 0.18)" />
              <stop offset="100%" stopColor="hsl(var(--ds-color-danger) / 0.25)" />
            </linearGradient>
          </defs>
          <rect x="0" y="0" width="100" height="100" fill="url(#riskGradient)" rx="2" />

          <text x="50" y="99" textAnchor="middle" fontSize="2.5" fill="hsl(var(--ds-color-muted-foreground))">Uncertainty →</text>
          <text x="1.5" y="50" textAnchor="middle" fontSize="2.5" fill="hsl(var(--ds-color-muted-foreground))" transform="rotate(-90,1.5,50)">Risk →</text>

          {[20, 40, 60, 80].map((line) => (
            <g key={line}>
              <line x1={line} y1={0} x2={line} y2={100} stroke="hsl(var(--ds-color-border) / 0.5)" strokeWidth="0.25" />
              <line x1={0} y1={line} x2={100} y2={line} stroke="hsl(var(--ds-color-border) / 0.5)" strokeWidth="0.25" />
            </g>
          ))}

          <rect x="82" y="0" width="18" height="18" fill="hsl(var(--destructive) / 0.08)" rx="1" />
          <text x="91" y="10" textAnchor="middle" fontSize="2" fill="hsl(var(--destructive) / 0.5)">CRITICAL</text>

          {filteredPoints.map((point) => {
            const x = point.uncertainty * 100;
            const y = (1 - point.risk) * 100;
            const cluster = getCluster(point);
            const isSelected = selectedPointId === point.id;
            const isHovered = hoveredPointId === point.id;
            const fill = pointFill(cluster);
            return (
              <g key={point.id}>
                {isSelected && (
                  <circle cx={x} cy={y} r="2.8" fill="none" stroke={fill} strokeWidth="0.4" opacity="0.6" />
                )}
                <circle
                  cx={x}
                  cy={y}
                  r={isSelected ? 1.6 : isHovered ? 1.4 : 1.1}
                  fill={fill}
                  opacity={cluster === "critical" ? 0.95 : cluster === "risky" ? 0.85 : 0.72}
                  className="cursor-pointer"
                  tabIndex={0}
                  role="button"
                  aria-label={`${cluster} point: Risk ${point.risk.toFixed(2)}, Uncertainty ${point.uncertainty.toFixed(2)}`}
                  onClick={() => onSelectPoint(point.id)}
                  onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectPoint(point.id); } }}
                  onMouseEnter={() => onHoverPoint(point.id)}
                  onMouseLeave={() => onHoverPoint(null)}
                  onFocus={() => onHoverPoint(point.id)}
                  onBlur={() => onHoverPoint(null)}
                >
                  <title>{`ID: ${point.id}\nRisk: ${point.risk.toFixed(2)} | Uncertainty: ${point.uncertainty.toFixed(2)}\nCluster: ${cluster}`}</title>
                </circle>
              </g>
            );
          })}
        </svg>

        {hoveredPoint && (
          <div className="pointer-events-none absolute left-4 top-4 z-10 max-w-xs rounded-lg border border-border/60 bg-background/95 px-3 py-2 text-xs shadow-lg" data-testid="hover-summary">
            <p className="font-mono text-[10px] text-muted-foreground">{hoveredPoint.id}</p>
            <p className="mt-0.5"><span className="text-muted-foreground">Risk:</span> <span className="font-semibold">{hoveredPoint.risk.toFixed(2)}</span> · <span className="text-muted-foreground">Uncertainty:</span> <span className="font-semibold">{hoveredPoint.uncertainty.toFixed(2)}</span></p>
            <p className="mt-0.5 text-muted-foreground">Cluster: <span className="font-semibold">{getCluster(hoveredPoint)}</span></p>
          </div>
        )}
      </div>
    </div>
  );
}
