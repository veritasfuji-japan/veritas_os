export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  service: string;
  timestamp: string;
}

export interface ApiError {
  code: string;
  message: string;
}

/**
 * Runtime check for `/health` response payloads.
 */
export function isHealthResponse(value: unknown): value is HealthResponse {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const response = value as Record<string, unknown>;

  return (
    (response.status === "ok" || response.status === "degraded" || response.status === "error") &&
    typeof response.service === "string" &&
    typeof response.timestamp === "string"
  );
}

export { isDecideResponse } from "./decision";

export type {
  DecideResponse,
  DecideResponseMeta,
  DecisionAlternative,
  DecisionStatus,
  EvidenceItem,
  GateOut,
  TrustLog,
  ValuesOut
} from "./decision";
