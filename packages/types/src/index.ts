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

export { isDecideResponse, isPersonaState, isEvoTips } from "./decision";

export type {
  ChatRequest,
  CritiqueItem,
  CritiqueSeverity,
  DebateView,
  DecideResponse,
  DecideResponseMeta,
  DecisionAlternative,
  DecisionStatus,
  EvidenceItem,
  EvoTips,
  FujiDecision,
  GateOut,
  MemoryKind,
  PersonaState,
  ResponseStyle,
  RetentionClass,
  TimeHorizon,
  TrustLog,
  ValuesOut
} from "./decision";

export type {
  AutoStop,
  FujiRules,
  GovernancePolicy,
  GovernancePolicyResponse,
  LogRetention,
  RiskThresholds,
} from "./governance";
