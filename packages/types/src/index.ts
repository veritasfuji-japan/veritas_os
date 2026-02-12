export interface HealthResponse {
  status: "ok" | "degraded" | "error";
  service: string;
  timestamp: string;
}

export interface ApiError {
  code: string;
  message: string;
}

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
