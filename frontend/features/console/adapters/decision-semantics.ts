const CANONICAL_GATE_DECISIONS = new Set([
  "proceed",
  "hold",
  "block",
  "human_review_required",
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
