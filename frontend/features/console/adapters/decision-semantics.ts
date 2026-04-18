const CANONICAL_GATE_DECISIONS = new Set([
  "proceed",
  "hold",
  "block",
  "human_review_required",
] as const);

const CANONICAL_BUSINESS_DECISIONS = new Set([
  "APPROVE",
  "DENY",
  "HOLD",
  "REVIEW_REQUIRED",
  "EVIDENCE_REQUIRED",
  "POLICY_DEFINITION_REQUIRED",
] as const);

const GATE_ALIAS_TO_CANONICAL: Record<string, string> = {
  allow: "proceed",
  deny: "block",
  rejected: "block",
  modify: "hold",
  abstain: "hold",
  proceed: "proceed",
  hold: "hold",
  block: "block",
  human_review_required: "human_review_required",
  unknown: "unknown",
};

const BUSINESS_ALIAS_TO_CANONICAL: Record<string, string> = {
  allow: "APPROVE",
  proceed: "APPROVE",
  approve: "APPROVE",
  deny: "DENY",
  rejected: "DENY",
  block: "DENY",
  hold: "HOLD",
  modify: "HOLD",
  abstain: "HOLD",
  review_required: "REVIEW_REQUIRED",
  ambiguous_human_review: "REVIEW_REQUIRED",
  evidence_required: "EVIDENCE_REQUIRED",
  policy_definition_required: "POLICY_DEFINITION_REQUIRED",
};

const NEXT_ACTION_ALIAS_TO_CANONICAL: Record<string, string> = {
  needs_human_review: "PREPARE_HUMAN_REVIEW_PACKET",
  reject_request: "DO_NOT_EXECUTE",
};

export function canonicalizePublicGateDecision(value: unknown): string {
  if (typeof value !== "string") {
    return "unknown";
  }
  const normalized = value.trim().toLowerCase();
  if (!normalized) {
    return "unknown";
  }
  const mapped = GATE_ALIAS_TO_CANONICAL[normalized] ?? normalized;
  return CANONICAL_GATE_DECISIONS.has(mapped as never) ? mapped : "unknown";
}

export function canonicalizeBusinessDecision(value: unknown): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized) {
    return "HOLD";
  }
  const upper = normalized.toUpperCase();
  if (CANONICAL_BUSINESS_DECISIONS.has(upper as never)) {
    return upper;
  }
  return BUSINESS_ALIAS_TO_CANONICAL[normalized.toLowerCase()] ?? "HOLD";
}

export function canonicalizeNextAction(value: unknown): string {
  const normalized = typeof value === "string" ? value.trim() : "";
  if (!normalized) {
    return "REVISE_AND_RESUBMIT";
  }
  const upper = normalized.toUpperCase();
  return NEXT_ACTION_ALIAS_TO_CANONICAL[upper.toLowerCase()] ?? upper;
}

export function gateDecisionLabel(gateDecision: string): string {
  if (gateDecision === "proceed") {
    return "proceed (execution guidance, not business approval)";
  }
  if (gateDecision === "hold") {
    return "gate hold";
  }
  if (gateDecision === "block") {
    return "blocked by gate";
  }
  if (gateDecision === "human_review_required") {
    return "human review required by gate";
  }
  return "gate status";
}
