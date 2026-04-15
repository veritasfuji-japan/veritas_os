import { type DecideResponse } from "@veritas/types";

/**
 * Financial governance sample fixture used for Mission Control UI regression.
 *
 * Mirrors the bundle sample added in backend governance templates while
 * including top-level console fields consumed by the frontend.
 */
export const financialHumanReviewFixture: DecideResponse = {
  ok: true,
  error: null,
  request_id: "fin-wire-2026-0001",
  version: "1.0",
  decision_status: "hold",
  gate_decision: "human_review_required",
  business_decision: "REVIEW_REQUIRED",
  next_action: "ROUTE_TO_HUMAN_REVIEW",
  required_evidence: [
    "kyc_verification",
    "source_of_funds_attestation",
    "aml_screening_receipt",
  ],
  missing_evidence: [
    "source_of_funds_attestation",
  ],
  human_review_required: true,
  rejection_reason: null,
  chosen: { id: "route_review", title: "Route to specialist review queue" },
  alternatives: [
    { id: "collect_then_retry", title: "Collect evidence and re-evaluate", value_score: 0.71 },
  ],
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
} as unknown as DecideResponse;
