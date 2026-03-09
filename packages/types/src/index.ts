export interface HealthResponse {
  ok: boolean;
  uptime: number;
  checks: {
    pipeline: string;
    memory: string;
  };
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

  if (typeof response.ok !== "boolean" || typeof response.uptime !== "number") {
    return false;
  }

  if (typeof response.checks !== "object" || response.checks === null) {
    return false;
  }

  const checks = response.checks as Record<string, unknown>;

  return typeof checks.pipeline === "string" && typeof checks.memory === "string";
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
