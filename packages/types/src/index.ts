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

export {
  isChatRequest,
  isCritiqueItem,
  isDebateView,
  isDecideRequest,
  isDecideResponse,
  isDecisionAlternative,
  isEvidenceItem,
  isEvoTips,
  isFujiDecision,
  isGateOut,
  isMemoryEraseRequest,
  isMemoryGetRequest,
  isMemoryPutRequest,
  isMemorySearchRequest,
  isPersonaState,
  isStageMetrics,
  isTrustFeedbackRequest,
  isValuesOut,
} from "./decision";

export type {
  ChatRequest,
  ComplianceConfigBody,
  ComplianceConfigResponse,
  Context,
  CritiqueItem,
  CritiqueSeverity,
  DebateView,
  DecideRequest,
  DecideResponse,
  DecideResponseMeta,
  DecisionAlternative,
  DecisionStatus,
  DeploymentReadinessResponse,
  EvidenceItem,
  EvoTips,
  FujiDecision,
  GateOut,
  GovernancePolicyHistoryResponse,
  MemoryEraseRequest,
  MemoryGetRequest,
  MemoryGetResponse,
  MemoryKind,
  MemoryPutRequest,
  MemoryPutResponse,
  MemorySearchRequest,
  Option,
  PersonaState,
  PolicyHistoryEntry,
  ReplayResponse,
  ResponseStyle,
  RetentionClass,
  StageHealth,
  StageMetrics,
  SystemHaltRequest,
  SystemHaltResponse,
  SystemHaltStatusResponse,
  SystemResumeRequest,
  SystemResumeResponse,
  TimeHorizon,
  TrustFeedbackRequest,
  TrustFeedbackResponse,
  TrustLog,
  TrustVerifyResponse,
  ValuesOut
} from "./decision";

export type {
  AuditLevel,
  AutoStop,
  FujiRules,
  GovernancePolicy,
  GovernancePolicyResponse,
  LogRetention,
  RiskThresholds,
} from "./governance";

export { isContinuationAssessment } from "./continuation";

export type {
  ContinuationAssessment,
  ContinuationClaim,
  ContinuationStatus,
  RefusalBoundary,
  SupportSnapshot,
  SupportStatus,
} from "./continuation";
