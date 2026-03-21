import type { RequestStatus, Severity } from "./risk-types";

export const STREAM_WINDOW_MS = 24 * 60 * 60 * 1000;
export const ALERT_CLUSTER_THRESHOLD = 0.82;
export const STREAM_TICK_MS = 2_000;
export const MAX_POINTS = 480;
export const RISK_CONFIDENCE_WEIGHT = 0.9;
export const UNCERTAINTY_CONFIDENCE_WEIGHT = 0.15;
export const UNSAFE_BURST_THRESHOLD = 6;
export const ELEVATED_RISK_THRESHOLD = 3;

export const SEVERITY_CLASSES: Record<Severity, string> = {
  critical: "bg-danger/15 text-danger border-danger/30",
  high: "bg-warning/15 text-warning border-warning/30",
  medium: "bg-info/15 text-info border-info/30",
  low: "bg-muted/20 text-muted-foreground border-border/40",
};

export const STATUS_LABELS: Record<RequestStatus, string> = {
  active: "Active",
  mitigated: "Mitigated",
  investigating: "Investigating",
  new: "New",
};
