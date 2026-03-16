import type { VerificationStatus } from "./audit-types";

export const PAGE_LIMIT = 50;

/* ------------------------------------------------------------------ */
/*  Status colors                                                      */
/* ------------------------------------------------------------------ */

export const STATUS_COLORS: Record<VerificationStatus, string> = {
  verified: "text-success",
  broken: "text-danger",
  missing: "text-warning",
  orphan: "text-info",
};

export const STATUS_BG: Record<VerificationStatus, string> = {
  verified: "bg-success/10 border-success/30",
  broken: "bg-danger/10 border-danger/30",
  missing: "bg-warning/10 border-warning/30",
  orphan: "bg-info/10 border-info/30",
};

export const STATUS_DOT: Record<VerificationStatus, string> = {
  verified: "bg-success",
  broken: "bg-danger",
  missing: "bg-warning",
  orphan: "bg-info",
};
