/**
 * Continuation Runtime types — Phase-1 (shadow-only).
 *
 * These types mirror the JSON schema at spec/continuation.schema.json and the
 * Python models in veritas_os/api/schemas.py.
 *
 * Phase-1 constraints:
 * - shadow_refusal is computed but never enforced.
 * - refusal_boundary is limited to "none" | "pre_tool_execution".
 * - The continuation field on DecideResponse is optional (null when feature
 *   flag is off).
 */

/** Lifecycle status of a continuation claim. */
export type ContinuationStatus = "active" | "narrowed" | "revoked" | "expired";

/** Whether the evidence basis for a claim still holds. */
export type SupportStatus = "valid" | "degraded" | "lost";

/**
 * Phase-1 refusal boundary.
 * - "none": no refusal.
 * - "pre_tool_execution": shadow-refusal before tool execution.
 */
export type RefusalBoundary = "none" | "pre_tool_execution";

/**
 * A claim that a prior decision's support still holds.
 *
 * Source of truth: spec/continuation.schema.json — ContinuationClaim
 */
export interface ContinuationClaim {
  claim_id: string;
  decision_request_id: string;
  support_basis: string[];
  created_at: string;
}

/**
 * A point-in-time snapshot of the evidence basis for a claim.
 *
 * Source of truth: spec/continuation.schema.json — SupportSnapshot
 */
export interface SupportSnapshot {
  claim_id: string;
  snapshot_at: string;
  support_status: SupportStatus;
  support_basis: string[];
}

/**
 * The Continuation Runtime's evaluation of a claim.
 *
 * Included in the /v1/decide response as the optional `continuation` field.
 *
 * Source of truth: spec/continuation.schema.json — ContinuationAssessment
 */
export interface ContinuationAssessment {
  claim_id: string;
  status: ContinuationStatus;
  support_status: SupportStatus;
  support_basis: string[];
  allowed_action_classes: string[];
  revocation_reason_code: string | null;
  /** Whether the runtime would refuse this action in enforcement mode. Shadow-only in phase-1. */
  shadow_refusal: boolean;
  /** Phase-1: limited to "none" | "pre_tool_execution". */
  refusal_boundary: RefusalBoundary;
}

// ---------------------------------------------------------------------------
// Runtime type guards
// ---------------------------------------------------------------------------

function isContinuationStatus(value: unknown): value is ContinuationStatus {
  return value === "active" || value === "narrowed" || value === "revoked" || value === "expired";
}

function isSupportStatus(value: unknown): value is SupportStatus {
  return value === "valid" || value === "degraded" || value === "lost";
}

function isRefusalBoundary(value: unknown): value is RefusalBoundary {
  return value === "none" || value === "pre_tool_execution";
}

/**
 * Runtime type guard for ContinuationAssessment payloads.
 */
export function isContinuationAssessment(value: unknown): value is ContinuationAssessment {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const v = value as Record<string, unknown>;

  return (
    typeof v.claim_id === "string" &&
    isContinuationStatus(v.status) &&
    isSupportStatus(v.support_status) &&
    Array.isArray(v.support_basis) &&
    v.support_basis.every((s: unknown) => typeof s === "string") &&
    Array.isArray(v.allowed_action_classes) &&
    v.allowed_action_classes.every((s: unknown) => typeof s === "string") &&
    (v.revocation_reason_code === null || typeof v.revocation_reason_code === "string") &&
    typeof v.shadow_refusal === "boolean" &&
    isRefusalBoundary(v.refusal_boundary)
  );
}
