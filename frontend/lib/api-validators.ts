import type {
  AuditLevel,
  GovernancePolicy,
  GovernancePolicyResponse,
  RequestLogResponse,
  RiskThresholds,
  TrustLog,
  TrustLogItem,
  TrustLogsResponse,
  VerificationResult,
} from "@veritas/types";

import {
  isTrustLog,
  isTrustLogItem,
  isTrustLogsResponse as _isTrustLogsResponseFromTypes,
  isRequestLogResponse as _isRequestLogResponseFromTypes,
} from "@veritas/types";

export type {
  AuditLevel,
  GovernancePolicy,
  GovernancePolicyResponse,
  RequestLogResponse,
  TrustLog,
  TrustLogItem,
  TrustLogsResponse,
  VerificationResult,
};

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

const AUDIT_LEVELS: ReadonlySet<AuditLevel> = new Set<AuditLevel>(["none", "minimal", "summary", "standard", "full", "strict"]);

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


function validateBooleanField(parent: Record<string, unknown>, key: string, pathPrefix: string): GovernanceValidationIssue[] {
  return hasBooleanField(parent, key) ? [] : [issue("format", `${pathPrefix}.${key}`, "boolean である必要があります。")];
}

function validateNumberField(parent: Record<string, unknown>, key: string, pathPrefix: string): GovernanceValidationIssue[] {
  return hasNumberField(parent, key) ? [] : [issue("format", `${pathPrefix}.${key}`, "number である必要があります。")];
}

function validateStringField(parent: Record<string, unknown>, key: string, pathPrefix: string): GovernanceValidationIssue[] {
  return hasStringField(parent, key) ? [] : [issue("format", `${pathPrefix}.${key}`, "string である必要があります。")];
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
  if (!isRecord(value.rollout_controls)) {
    issues.push(issue("format", `${pathPrefix}.rollout_controls`, "object である必要があります。"));
  } else {
    const strategy = value.rollout_controls.strategy;
    if (typeof strategy !== "string") {
      issues.push(issue("format", `${pathPrefix}.rollout_controls.strategy`, "string である必要があります。"));
    }
    if (!hasNumberField(value.rollout_controls, "canary_percent")) {
      issues.push(issue("format", `${pathPrefix}.rollout_controls.canary_percent`, "number である必要があります。"));
    }
    if (!hasNumberField(value.rollout_controls, "stage")) {
      issues.push(issue("format", `${pathPrefix}.rollout_controls.stage`, "number である必要があります。"));
    }
    if (!hasBooleanField(value.rollout_controls, "staged_enforcement")) {
      issues.push(issue("format", `${pathPrefix}.rollout_controls.staged_enforcement`, "boolean である必要があります。"));
    }
  }

  if (!isRecord(value.approval_workflow)) {
    issues.push(issue("format", `${pathPrefix}.approval_workflow`, "object である必要があります。"));
  } else {
    if (!hasStringField(value.approval_workflow, "human_review_ticket")) {
      issues.push(issue("format", `${pathPrefix}.approval_workflow.human_review_ticket`, "string である必要があります。"));
    }
    if (!hasBooleanField(value.approval_workflow, "human_review_required")) {
      issues.push(issue("format", `${pathPrefix}.approval_workflow.human_review_required`, "boolean である必要があります。"));
    }
    if (!hasBooleanField(value.approval_workflow, "approver_identity_binding")) {
      issues.push(issue("format", `${pathPrefix}.approval_workflow.approver_identity_binding`, "boolean である必要があります。"));
    }
    if (
      !Array.isArray(value.approval_workflow.approver_identities)
      || !value.approval_workflow.approver_identities.every((item) => typeof item === "string")
    ) {
      issues.push(issue("format", `${pathPrefix}.approval_workflow.approver_identities`, "string の配列である必要があります。"));
    }
  }

  if (!isRecord(value.wat)) {
    issues.push(issue("format", `${pathPrefix}.wat`, "object である必要があります。"));
  } else {
    issues.push(...validateBooleanField(value.wat, "enabled", `${pathPrefix}.wat`));
    issues.push(...validateStringField(value.wat, "issuance_mode", `${pathPrefix}.wat`));
    issues.push(...validateNumberField(value.wat, "wat_metadata_retention_ttl_seconds", `${pathPrefix}.wat`));
    issues.push(...validateNumberField(value.wat, "wat_event_pointer_retention_ttl_seconds", `${pathPrefix}.wat`));
    issues.push(...validateNumberField(value.wat, "observable_digest_retention_ttl_seconds", `${pathPrefix}.wat`));
    issues.push(...validateStringField(value.wat, "retention_policy_version", `${pathPrefix}.wat`));
    issues.push(...validateBooleanField(value.wat, "retention_enforced_at_write", `${pathPrefix}.wat`));
  }

  if (!isRecord(value.shadow_validation)) {
    issues.push(issue("format", `${pathPrefix}.shadow_validation`, "object である必要があります。"));
  } else {
    issues.push(...validateStringField(value.shadow_validation, "partial_validation_default", `${pathPrefix}.shadow_validation`));
    issues.push(...validateBooleanField(value.shadow_validation, "replay_binding_required", `${pathPrefix}.shadow_validation`));
    issues.push(...validateNumberField(value.shadow_validation, "replay_binding_escalation_threshold", `${pathPrefix}.shadow_validation`));
    issues.push(...validateBooleanField(value.shadow_validation, "partial_validation_requires_confirmation", `${pathPrefix}.shadow_validation`));
  }

  if (!isRecord(value.revocation)) {
    issues.push(issue("format", `${pathPrefix}.revocation`, "object である必要があります。"));
  } else {
    issues.push(...validateStringField(value.revocation, "mode", `${pathPrefix}.revocation`));
    issues.push(...validateBooleanField(value.revocation, "revocation_confirmation_required", `${pathPrefix}.revocation`));
    issues.push(...validateBooleanField(value.revocation, "auto_escalate_confirmed_revocations", `${pathPrefix}.revocation`));
  }

  if (!hasStringField(value, "operator_verbosity")) {
    issues.push(issue("format", `${pathPrefix}.operator_verbosity`, "string である必要があります。"));
  } else if (value.operator_verbosity !== "minimal" && value.operator_verbosity !== "expanded") {
    issues.push(issue("semantic", `${pathPrefix}.operator_verbosity`, "minimal または expanded である必要があります。"));
  }

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

// ----------------------------------------------------------------
// Trust-log validators: re-exported from @veritas/types
// ----------------------------------------------------------------

export { isTrustLog, isTrustLogItem };

/**
 * Runtime type guard for TrustLogsResponse payloads.
 * Re-exported from @veritas/types for backward compatibility.
 */
export const isTrustLogsResponse = _isTrustLogsResponseFromTypes;

/**
 * Runtime type guard for RequestLogResponse payloads.
 * Re-exported from @veritas/types for backward compatibility.
 */
export const isRequestLogResponse = _isRequestLogResponseFromTypes;
