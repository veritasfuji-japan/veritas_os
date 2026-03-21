"use client";

const RISK_BAND_BG: Record<string, string> = {
  danger: "bg-danger",
  warning: "bg-warning",
  success: "bg-success",
};

const RISK_BAND_TEXT: Record<string, string> = {
  danger: "text-danger",
  warning: "text-warning",
  success: "text-success",
};

function riskBand(value: number): string {
  if (value > 75) return "danger";
  if (value > 50) return "warning";
  return "success";
}

interface RiskImpactGaugeProps {
  current: number;
  pending: number;
  drift: number;
}

export function RiskImpactGauge({ current, pending, drift }: RiskImpactGaugeProps): JSX.Element {
  const band = riskBand(current);
  const pendingBand = riskBand(pending);
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold w-28">Current Policy</span>
        <div className="flex-1 rounded-full bg-muted h-2.5 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${RISK_BAND_BG[band]}`} style={{ width: `${current}%` }} />
        </div>
        <span className={`text-xs font-mono font-semibold ${RISK_BAND_TEXT[band]}`}>{current}%</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold w-28">Pending Impact</span>
        <div className="flex-1 rounded-full bg-muted h-2.5 overflow-hidden">
          <div className={`h-full rounded-full transition-all ${RISK_BAND_BG[pendingBand]}`} style={{ width: `${pending}%` }} />
        </div>
        <span className={`text-xs font-mono font-semibold ${RISK_BAND_TEXT[pendingBand]}`}>{pending}%</span>
      </div>
      <div className="flex items-center gap-3">
        <span className="text-xs font-semibold w-28">Recent Drift</span>
        <span className={`text-xs font-mono font-semibold ${drift > 5 ? "text-warning" : "text-success"}`}>
          {drift > 0 ? `+${drift}%` : `${drift}%`} from baseline
        </span>
      </div>
    </div>
  );
}
