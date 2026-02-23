interface FujiRules {
  pii_check: boolean;
  self_harm_block: boolean;
  illicit_block: boolean;
  violence_review: boolean;
  minors_review: boolean;
  keyword_hard_block: boolean;
  keyword_soft_flag: boolean;
  llm_safety_head: boolean;
}

interface RiskThresholds {
  allow_upper: number;
  warn_upper: number;
  human_review_upper: number;
  deny_upper: number;
}

interface AutoStop {
  enabled: boolean;
  max_risk_score: number;
  max_consecutive_rejects: number;
  max_requests_per_minute: number;
}

interface LogRetention {
  retention_days: number;
  audit_level: string;
  include_fields: string[];
  redact_before_log: boolean;
  max_log_size: number;
}

export interface GovernancePolicy {
  version: string;
  fuji_rules: FujiRules;
  risk_thresholds: RiskThresholds;
  auto_stop: AutoStop;
  log_retention: LogRetention;
  updated_at: string;
  updated_by: string;
}

export interface GovernancePolicyResponse {
  ok: boolean;
  policy: GovernancePolicy;
}

export interface TrustLogItem {
  request_id?: string;
  created_at?: string;
  stage?: string;
  sha256?: string;
  sha256_prev?: string;
  [key: string]: unknown;
}

export interface TrustLogsResponse {
  items: TrustLogItem[];
  cursor: string;
  next_cursor: string | null;
  limit: number;
  has_more: boolean;
}

export interface RequestLogResponse {
  request_id: string;
  items: TrustLogItem[];
  count: number;
  chain_ok: boolean;
  verification_result: string;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function hasBooleanField(obj: Record<string, unknown>, key: string): boolean {
  return typeof obj[key] === "boolean";
}

function hasNumberField(obj: Record<string, unknown>, key: string): boolean {
  return typeof obj[key] === "number" && Number.isFinite(obj[key]);
}

function hasStringField(obj: Record<string, unknown>, key: string): boolean {
  return typeof obj[key] === "string";
}

function isFujiRules(value: unknown): value is FujiRules {
  if (!isRecord(value)) {
    return false;
  }

  return [
    "pii_check",
    "self_harm_block",
    "illicit_block",
    "violence_review",
    "minors_review",
    "keyword_hard_block",
    "keyword_soft_flag",
    "llm_safety_head",
  ].every((key) => hasBooleanField(value, key));
}

function isRiskThresholds(value: unknown): value is RiskThresholds {
  if (!isRecord(value)) {
    return false;
  }

  return ["allow_upper", "warn_upper", "human_review_upper", "deny_upper"].every((key) => hasNumberField(value, key));
}

function isAutoStop(value: unknown): value is AutoStop {
  if (!isRecord(value)) {
    return false;
  }

  return (
    hasBooleanField(value, "enabled")
    && hasNumberField(value, "max_risk_score")
    && hasNumberField(value, "max_consecutive_rejects")
    && hasNumberField(value, "max_requests_per_minute")
  );
}

function isLogRetention(value: unknown): value is LogRetention {
  if (!isRecord(value)) {
    return false;
  }

  return (
    hasNumberField(value, "retention_days")
    && hasStringField(value, "audit_level")
    && Array.isArray(value.include_fields)
    && value.include_fields.every((field) => typeof field === "string")
    && hasBooleanField(value, "redact_before_log")
    && hasNumberField(value, "max_log_size")
  );
}

export function isGovernancePolicy(value: unknown): value is GovernancePolicy {
  if (!isRecord(value)) {
    return false;
  }

  return (
    hasStringField(value, "version")
    && isFujiRules(value.fuji_rules)
    && isRiskThresholds(value.risk_thresholds)
    && isAutoStop(value.auto_stop)
    && isLogRetention(value.log_retention)
    && hasStringField(value, "updated_at")
    && hasStringField(value, "updated_by")
  );
}

export function isGovernancePolicyResponse(value: unknown): value is GovernancePolicyResponse {
  if (!isRecord(value)) {
    return false;
  }

  return typeof value.ok === "boolean" && isGovernancePolicy(value.policy);
}

export function isTrustLogItem(value: unknown): value is TrustLogItem {
  if (!isRecord(value)) {
    return false;
  }

  if (value.request_id !== undefined && typeof value.request_id !== "string") {
    return false;
  }

  if (value.created_at !== undefined && typeof value.created_at !== "string") {
    return false;
  }

  if (value.stage !== undefined && typeof value.stage !== "string") {
    return false;
  }

  if (value.sha256 !== undefined && typeof value.sha256 !== "string") {
    return false;
  }

  if (value.sha256_prev !== undefined && typeof value.sha256_prev !== "string") {
    return false;
  }

  return true;
}

export function isTrustLogsResponse(value: unknown): value is TrustLogsResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    Array.isArray(value.items)
    && value.items.every((item) => isTrustLogItem(item))
    && hasStringField(value, "cursor")
    && (value.next_cursor === null || typeof value.next_cursor === "string")
    && hasNumberField(value, "limit")
    && hasBooleanField(value, "has_more")
  );
}

export function isRequestLogResponse(value: unknown): value is RequestLogResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    hasStringField(value, "request_id")
    && Array.isArray(value.items)
    && value.items.every((item) => isTrustLogItem(item))
    && hasNumberField(value, "count")
    && hasBooleanField(value, "chain_ok")
    && hasStringField(value, "verification_result")
  );
}
