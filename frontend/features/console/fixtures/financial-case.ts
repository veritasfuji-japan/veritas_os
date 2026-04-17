import { type DecideResponse } from "@veritas/types";

function createFixture(overrides: Record<string, unknown>): DecideResponse {
  return {
    ok: true,
    error: null,
    request_id: "fin-wire-2026-0001",
    version: "1.0",
    decision_status: "hold",
    gate_decision: "human_review_required",
    business_decision: "REVIEW_REQUIRED",
    next_action: "ROUTE_TO_HUMAN_REVIEW",
    required_evidence: ["kyc_verification", "source_of_funds_attestation", "aml_screening_receipt"],
    missing_evidence: ["source_of_funds_attestation"],
    human_review_required: true,
    rejection_reason: null,
    chosen: { id: "route_review", title: "Route to specialist review queue" },
    alternatives: [{ id: "collect_then_retry", title: "Collect evidence and re-evaluate", value_score: 0.71 }],
    options: [],
    fuji: { decision_status: "hold", rule_hit: "financial.high_risk_wire_transfer" },
    gate: { decision_status: "hold", risk: 0.74, severity: "high" },
    evidence: [{ source: "kyc_system", snippet: "Incomplete source of funds file", confidence: 0.92 }],
    critique: [],
    debate: [],
    telos_score: 0.68,
    values: { total: 0.72, rationale: "Human oversight required for high-risk transaction." },
    plan: null,
    planner: null,
    persona: {},
    memory_citations: [],
    memory_used_count: 0,
    trust_log: null,
    extras: {},
    meta: {},
    ai_disclosure: "",
    regulation_notice: "",
    reason: null,
    rsi_note: null,
    evo: null,
    active_posture: "strict",
    backend: "gpt-5.3-mini",
    verify_status: "anchored",
    ...overrides,
  } as unknown as DecideResponse;
}

/** Baseline financial scenario requiring human review. */
export const financialHumanReviewFixture = createFixture({});

/** Block scenario for high-risk policy violations. */
export const financialBlockFixture = createFixture({
  request_id: "fin-wire-2026-block",
  decision_status: "deny",
  gate_decision: "block",
  business_decision: "DENY",
  next_action: "DO_NOT_EXECUTE",
  required_evidence: ["regulatory_exception_ticket"],
  missing_evidence: ["regulatory_exception_ticket"],
  human_review_required: true,
  gate: { decision_status: "block", risk: 0.96, severity: "critical", reason: "Sanctions match unresolved" },
  fuji: { decision_status: "block", rule_hit: "financial.sanctions_hit" },
  values: { total: 0.19, rationale: "Risk exceeds permitted threshold." },
});

/** Proceed scenario for low-risk operation. */
export const financialProceedFixture = createFixture({
  request_id: "fin-wire-2026-proceed",
  decision_status: "allow",
  gate_decision: "allow",
  business_decision: "APPROVE",
  next_action: "EXECUTE_WITH_STANDARD_MONITORING",
  required_evidence: ["kyc_verification"],
  missing_evidence: [],
  human_review_required: false,
  chosen: { id: "approve", title: "Proceed with transfer" },
  values: { total: 0.91, rationale: "All controls satisfied." },
});

/** Evidence-required scenario where collection should happen before execution. */
export const financialEvidenceRequiredFixture = createFixture({
  request_id: "fin-wire-2026-evidence-required",
  decision_status: "hold",
  gate_decision: "hold",
  business_decision: "EVIDENCE_REQUIRED",
  next_action: "COLLECT_EVIDENCE_AND_REEVALUATE",
  required_evidence: ["source_of_funds_attestation", "beneficiary_verification"],
  missing_evidence: ["source_of_funds_attestation", "beneficiary_verification"],
  human_review_required: false,
  values: { total: 0.42, rationale: "Decision quality is bounded by missing evidence." },
});

/** Ambiguity scenario where human review is required despite moderate risk. */
export const financialAmbiguityHumanReviewFixture = createFixture({
  request_id: "fin-wire-2026-ambiguity",
  decision_status: "hold",
  gate_decision: "human_review_required",
  business_decision: "AMBIGUOUS_HUMAN_REVIEW",
  next_action: "ROUTE_TO_HUMAN_REVIEW",
  required_evidence: ["analyst_commentary", "beneficiary_background"],
  missing_evidence: ["analyst_commentary"],
  human_review_required: true,
  gate: { decision_status: "hold", risk: 0.64, severity: "medium", reason: "Conflicting risk indicators" },
  values: { total: 0.56, rationale: "Ambiguous risk signals need reviewer judgment." },
});
