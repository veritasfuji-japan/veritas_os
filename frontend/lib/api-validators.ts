import type {
  AuditLevel,
  AutoStop,
  FujiRules,
  GovernancePolicy,
  GovernancePolicyResponse,
  LogRetention,
  RiskThresholds,
  TrustLog,
} from "@veritas/types";

export type { AuditLevel, GovernancePolicy, GovernancePolicyResponse, TrustLog };

export interface GovernanceValidationIssue {
  category: "format" | "semantic";
  path: string;
  message: string;
}

interface GovernanceValidationSuccess {
  ok: true;
  data: GovernancePolicyResponse;
}

interface GovernanceValidationFailure {
  ok: false;
  issues: GovernanceValidationIssue[];
}

export type GovernanceValidationResult = GovernanceValidationSuccess | GovernanceValidationFailure;

const AUDIT_LEVELS: ReadonlySet<AuditLevel> = new Set<AuditLevel>(["none", "minimal", "standard", "full", "strict"]);

/** @deprecated Use TrustLog from @veritas/types directly. */
export type TrustLogItem = TrustLog;

export interface TrustLogsResponse {
  items: TrustLog[];
  cursor: string;
  next_cursor: string | null;
  limit: number;
  has_more: boolean;
}

export interface RequestLogResponse {
  request_id: string;
  items: TrustLog[];
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

function isIso8601WithOffset(value: string): boolean {
  const isoPattern = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;
  if (!isoPattern.test(value)) {
    return false;
  }

  return !Number.isNaN(Date.parse(value));
}

function issue(category: "format" | "semantic", path: string, message: string): GovernanceValidationIssue {
  return { category, path, message };
}

function validateFujiRules(value: unknown, pathPrefix: string): GovernanceValidationIssue[] {
  if (!isRecord(value)) {
    return [issue("format", pathPrefix, "object である必要があります。")];
  }

  const keys = [
    "pii_check",
    "self_harm_block",
    "illicit_block",
    "violence_review",
    "minors_review",
    "keyword_hard_block",
    "keyword_soft_flag",
    "llm_safety_head",
  ];

  return keys
    .filter((key) => !hasBooleanField(value, key))
    .map((key) => issue("format", `${pathPrefix}.${key}`, "boolean である必要があります。"));
}

function validateThresholdValue(
  obj: Record<string, unknown>,
  key: keyof RiskThresholds,
  pathPrefix: string,
): GovernanceValidationIssue[] {
  const path = `${pathPrefix}.${key}`;
  if (!hasNumberField(obj, key)) {
    return [issue("format", path, "number である必要があります。")];
  }

  const num = obj[key] as number;
  if (num < 0 || num > 1) {
    return [issue("semantic", path, "0 以上 1 以下である必要があります。")];
  }

  return [];
}

function validateRiskThresholds(value: unknown, pathPrefix: string): GovernanceValidationIssue[] {
  if (!isRecord(value)) {
    return [issue("format", pathPrefix, "object である必要があります。")];
  }

  const issues = [
    ...validateThresholdValue(value, "allow_upper", pathPrefix),
    ...validateThresholdValue(value, "warn_upper", pathPrefix),
    ...validateThresholdValue(value, "human_review_upper", pathPrefix),
    ...validateThresholdValue(value, "deny_upper", pathPrefix),
  ];

  const hasAllThresholds = ["allow_upper", "warn_upper", "human_review_upper", "deny_upper"].every((key) => hasNumberField(value, key));
  if (!hasAllThresholds) {
    return issues;
  }

  const allowUpper = value.allow_upper as number;
  const warnUpper = value.warn_upper as number;
  const humanReviewUpper = value.human_review_upper as number;
  const denyUpper = value.deny_upper as number;

  if (allowUpper > warnUpper) {
    issues.push(issue("semantic", `${pathPrefix}.warn_upper`, "allow_upper <= warn_upper を満たしてください。"));
  }

  if (warnUpper > humanReviewUpper) {
    issues.push(issue("semantic", `${pathPrefix}.human_review_upper`, "warn_upper <= human_review_upper を満たしてください。"));
  }

  if (humanReviewUpper > denyUpper) {
    issues.push(issue("semantic", `${pathPrefix}.deny_upper`, "human_review_upper <= deny_upper を満たしてください。"));
  }

  return issues;
}

function validateAutoStop(value: unknown, pathPrefix: string): GovernanceValidationIssue[] {
  if (!isRecord(value)) {
    return [issue("format", pathPrefix, "object である必要があります。")];
  }

  const issues: GovernanceValidationIssue[] = [];

  if (!hasBooleanField(value, "enabled")) {
    issues.push(issue("format", `${pathPrefix}.enabled`, "boolean である必要があります。"));
  }

  if (!hasNumberField(value, "max_risk_score")) {
    issues.push(issue("format", `${pathPrefix}.max_risk_score`, "number である必要があります。"));
  } else {
    const score = value.max_risk_score as number;
    if (score < 0 || score > 1) {
      issues.push(issue("semantic", `${pathPrefix}.max_risk_score`, "0 以上 1 以下である必要があります。"));
    }
  }

  if (!hasNumberField(value, "max_consecutive_rejects")) {
    issues.push(issue("format", `${pathPrefix}.max_consecutive_rejects`, "number である必要があります。"));
  } else {
    const maxConsecutiveRejects = value.max_consecutive_rejects as number;
    if (!Number.isInteger(maxConsecutiveRejects) || maxConsecutiveRejects < 1 || maxConsecutiveRejects > 1000) {
      issues.push(issue("semantic", `${pathPrefix}.max_consecutive_rejects`, "1 以上 1000 以下の整数である必要があります。"));
    }
  }

  if (!hasNumberField(value, "max_requests_per_minute")) {
    issues.push(issue("format", `${pathPrefix}.max_requests_per_minute`, "number である必要があります。"));
  } else {
    const maxRequestsPerMinute = value.max_requests_per_minute as number;
    if (!Number.isInteger(maxRequestsPerMinute) || maxRequestsPerMinute < 1 || maxRequestsPerMinute > 10000) {
      issues.push(issue("semantic", `${pathPrefix}.max_requests_per_minute`, "1 以上 10000 以下の整数である必要があります。"));
    }
  }

  return issues;
}

function validateLogRetention(value: unknown, pathPrefix: string): GovernanceValidationIssue[] {
  if (!isRecord(value)) {
    return [issue("format", pathPrefix, "object である必要があります。")];
  }

  const issues: GovernanceValidationIssue[] = [];

  if (!hasNumberField(value, "retention_days")) {
    issues.push(issue("format", `${pathPrefix}.retention_days`, "number である必要があります。"));
  } else {
    const retentionDays = value.retention_days as number;
    if (!Number.isInteger(retentionDays) || retentionDays < 1 || retentionDays > 3650) {
      issues.push(issue("semantic", `${pathPrefix}.retention_days`, "1 以上 3650 以下の整数である必要があります。"));
    }
  }

  if (!hasStringField(value, "audit_level")) {
    issues.push(issue("format", `${pathPrefix}.audit_level`, "string である必要があります。"));
  } else if (!AUDIT_LEVELS.has(value.audit_level as AuditLevel)) {
    issues.push(issue("semantic", `${pathPrefix}.audit_level`, `許可された監査レベル (${[...AUDIT_LEVELS].join(", ")}) ではありません。`));
  }

  if (!Array.isArray(value.include_fields) || !value.include_fields.every((field) => typeof field === "string")) {
    issues.push(issue("format", `${pathPrefix}.include_fields`, "string の配列である必要があります。"));
  }

  if (!hasBooleanField(value, "redact_before_log")) {
    issues.push(issue("format", `${pathPrefix}.redact_before_log`, "boolean である必要があります。"));
  }

  if (!hasNumberField(value, "max_log_size")) {
    issues.push(issue("format", `${pathPrefix}.max_log_size`, "number である必要があります。"));
  } else {
    const maxLogSize = value.max_log_size as number;
    if (!Number.isInteger(maxLogSize) || maxLogSize < 100 || maxLogSize > 1000000) {
      issues.push(issue("semantic", `${pathPrefix}.max_log_size`, "100 以上 1000000 以下の整数である必要があります。"));
    }
  }

  return issues;
}

function validateGovernancePolicy(value: unknown, pathPrefix: string): GovernanceValidationIssue[] {
  if (!isRecord(value)) {
    return [issue("format", pathPrefix, "object である必要があります。")];
  }

  const issues: GovernanceValidationIssue[] = [];

  if (!hasStringField(value, "version")) {
    issues.push(issue("format", `${pathPrefix}.version`, "string である必要があります。"));
  }

  issues.push(...validateFujiRules(value.fuji_rules, `${pathPrefix}.fuji_rules`));
  issues.push(...validateRiskThresholds(value.risk_thresholds, `${pathPrefix}.risk_thresholds`));
  issues.push(...validateAutoStop(value.auto_stop, `${pathPrefix}.auto_stop`));
  issues.push(...validateLogRetention(value.log_retention, `${pathPrefix}.log_retention`));

  if (!hasStringField(value, "updated_at")) {
    issues.push(issue("format", `${pathPrefix}.updated_at`, "string である必要があります。"));
  } else if (!isIso8601WithOffset(value.updated_at as string)) {
    issues.push(issue("semantic", `${pathPrefix}.updated_at`, "ISO 8601 形式である必要があります。"));
  }

  if (!hasStringField(value, "updated_by")) {
    issues.push(issue("format", `${pathPrefix}.updated_by`, "string である必要があります。"));
  }

  return issues;
}

/**
 * Validate governance API payloads and classify failures into format vs semantic issues
 * so the UI can present actionable error messages to operators.
 */
export function validateGovernancePolicyResponse(value: unknown): GovernanceValidationResult {
  if (!isRecord(value)) {
    return {
      ok: false,
      issues: [issue("format", "policy_response", "object である必要があります。")],
    };
  }

  const issues: GovernanceValidationIssue[] = [];

  if (!hasBooleanField(value, "ok")) {
    issues.push(issue("format", "ok", "boolean である必要があります。"));
  }

  issues.push(...validateGovernancePolicy(value.policy, "policy"));

  if (issues.length > 0) {
    return {
      ok: false,
      issues,
    };
  }

  return {
    ok: true,
    data: {
      ok: value.ok as boolean,
      policy: value.policy as GovernancePolicy,
    },
  };
}

export function isGovernancePolicy(value: unknown): value is GovernancePolicy {
  return validateGovernancePolicy(value, "policy").length === 0;
}

export function isGovernancePolicyResponse(value: unknown): value is GovernancePolicyResponse {
  return validateGovernancePolicyResponse(value).ok;
}

function isStringArray(value: unknown): boolean {
  return Array.isArray(value) && value.every((s) => typeof s === "string");
}

/**
 * Runtime type guard for TrustLog payloads.
 * Validates the shared TrustLog type from @veritas/types,
 * used for both /v1/decide embedded trust_log and /v1/trust/logs list items.
 */
export function isTrustLog(value: unknown): value is TrustLog {
  if (!isRecord(value)) {
    return false;
  }

  if (typeof value.request_id !== "string") {
    return false;
  }

  if (typeof value.created_at !== "string") {
    return false;
  }

  if (!isStringArray(value.sources) || !isStringArray(value.critics) || !isStringArray(value.checks)) {
    return false;
  }

  if (typeof value.approver !== "string") {
    return false;
  }

  if (value.fuji !== undefined && value.fuji !== null && !isRecord(value.fuji)) {
    return false;
  }

  if (value.sha256 !== undefined && value.sha256 !== null && typeof value.sha256 !== "string") {
    return false;
  }

  if (value.sha256_prev !== undefined && value.sha256_prev !== null && typeof value.sha256_prev !== "string") {
    return false;
  }

  if (value.query !== undefined && value.query !== null && typeof value.query !== "string") {
    return false;
  }

  if (value.gate_status !== undefined && value.gate_status !== null && typeof value.gate_status !== "string") {
    return false;
  }

  if (value.gate_risk !== undefined && value.gate_risk !== null && typeof value.gate_risk !== "number") {
    return false;
  }

  return true;
}

/** @deprecated Use isTrustLog instead. */
export const isTrustLogItem = isTrustLog;

export function isTrustLogsResponse(value: unknown): value is TrustLogsResponse {
  if (!isRecord(value)) {
    return false;
  }

  return (
    Array.isArray(value.items)
    && value.items.every((item) => isTrustLog(item))
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
    && value.items.every((item) => isTrustLog(item))
    && hasNumberField(value, "count")
    && hasBooleanField(value, "chain_ok")
    && hasStringField(value, "verification_result")
  );
}
