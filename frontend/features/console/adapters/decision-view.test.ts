import { type DecideResponse } from "@veritas/types";
import { describe, expect, it } from "vitest";
import {
  toDecisionResultView,
  toEvidenceBundleDraft,
  toFujiGateDetailView,
  toPublicDecisionSchemaView,
  toRuntimeStatusView,
} from "./decision-view";

function makeResponse(overrides: Partial<DecideResponse> = {}): DecideResponse {
  return {
    ok: true,
    error: null,
    request_id: "req-test",
    version: "1.0",
    decision_status: "allow",
    rejection_reason: null,
    chosen: { id: "a1", title: "Option A" },
    alternatives: [{ id: "a1" }, { id: "b1", title: "Option B", value_score: 0.6 }],
    options: [],
    fuji: { decision_status: "allow" },
    gate: { decision_status: "allow", risk: 0.3 },
    evidence: [{ source: "doc", snippet: "s", confidence: 0.9 }],
    critique: [],
    debate: [],
    telos_score: 0.9,
    values: { total: 0.85, rationale: "High utility." },
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
    ...overrides,
  } as unknown as DecideResponse;
}

describe("toDecisionResultView", () => {
  it("extracts value score for chosen from values.total", () => {
    const result = makeResponse({ values: { total: 0.85, rationale: "Good" } as never });
    const view = toDecisionResultView(result);
    expect(view.chosen.valueScore).toBe(0.85);
  });

  it("returns null valueScore when values.total is missing", () => {
    const result = makeResponse({ values: { rationale: "No total" } as never });
    const view = toDecisionResultView(result);
    expect(view.chosen.valueScore).toBeNull();
  });

  it("extracts value_score from alternatives", () => {
    const result = makeResponse({
      alternatives: [
        { id: "b1", title: "Option B", value_score: 0.6 },
        { id: "c1", title: "Option C", score: 0.4 },
        { id: "d1", title: "Option D" },
      ] as never[],
    });
    const view = toDecisionResultView(result);
    expect(view.alternatives[0].valueScore).toBe(0.6);
    expect(view.alternatives[1].valueScore).toBe(0.4);
    expect(view.alternatives[2].valueScore).toBeNull();
  });
});

describe("toFujiGateDetailView", () => {
  it("returns empty drilldown for null result", () => {
    const view = toFujiGateDetailView(null);
    expect(view.riskScore).toBeNull();
    expect(view.reasons).toEqual([]);
    expect(view.violations).toEqual([]);
  });

  it("extracts risk score from gate.risk", () => {
    const result = makeResponse({ gate: { decision_status: "allow", risk: 0.65 } as never });
    const view = toFujiGateDetailView(result);
    expect(view.riskScore).toBe(0.65);
  });

  it("extracts risk score from fuji.risk_score when gate.risk is absent", () => {
    const result = makeResponse({
      fuji: { decision_status: "rejected", risk_score: 0.8 } as never,
      gate: { decision_status: "rejected" } as never,
    });
    const view = toFujiGateDetailView(result);
    expect(view.riskScore).toBe(0.8);
  });

  it("extracts reasons array", () => {
    const result = makeResponse({
      fuji: { decision_status: "rejected", reasons: ["PII detected", "Low evidence"] } as never,
    });
    const view = toFujiGateDetailView(result);
    expect(view.reasons).toEqual(["PII detected", "Low evidence"]);
  });

  it("filters non-string reasons", () => {
    const result = makeResponse({
      fuji: { decision_status: "block", reasons: ["Valid", 42, null, "Also valid"] } as never,
    });
    const view = toFujiGateDetailView(result);
    expect(view.reasons).toEqual(["Valid", "Also valid"]);
  });

  it("extracts violations with fallback fields", () => {
    const result = makeResponse({
      fuji: {
        decision_status: "block",
        violations: [
          { rule: "PII_RULE", detail: "Email detected", severity: "high" },
          { code: "ILLICIT", description: "Harmful content", level: "critical" },
        ],
      } as never,
    });
    const view = toFujiGateDetailView(result);
    expect(view.violations).toHaveLength(2);
    expect(view.violations[0]).toEqual({ rule: "PII_RULE", detail: "Email detected", severity: "high" });
    expect(view.violations[1]).toEqual({ rule: "ILLICIT", detail: "Harmful content", severity: "critical" });
  });

  it("returns empty violations when not present", () => {
    const result = makeResponse();
    const view = toFujiGateDetailView(result);
    expect(view.violations).toEqual([]);
  });
});

describe("toPublicDecisionSchemaView", () => {
  it("separates gate_decision from business_decision and next_action", () => {
    const result = makeResponse({
      gate_decision: "allow",
      business_decision: "REVIEW_REQUIRED",
      next_action: "ROUTE_TO_HUMAN_REVIEW",
      required_evidence: ["approval_ticket"],
      missing_evidence: ["approval_ticket"],
      human_review_required: true,
      active_posture: "strict",
      backend: "gpt-5.3-mini",
      verify_status: "verified",
    } as never);
    const view = toPublicDecisionSchemaView(result);
    expect(view.gateDecision).toBe("proceed");
    expect(view.businessDecision).toBe("REVIEW_REQUIRED");
    expect(view.nextAction).toBe("ROUTE_TO_HUMAN_REVIEW");
    expect(view.requiredEvidence).toEqual(["approval_ticket"]);
    expect(view.missingEvidence).toEqual(["approval_ticket"]);
    expect(view.humanReviewRequired).toBe(true);
    expect(view.activePosture).toBe("strict");
    expect(view.backend).toBe("gpt-5.3-mini");
    expect(view.verifyStatus).toBe("verified");
  });

  it("adds canonical label for proceed gate to avoid approval confusion", () => {
    const result = makeResponse({ gate_decision: "allow" } as never);
    const view = toPublicDecisionSchemaView(result);
    expect(view.gateDecisionLabel).toBe("proceed (execution guidance, not business approval)");
  });

  it("falls back to unknown for non-canonical gate outputs", () => {
    const result = makeResponse({ gate_decision: "totally_custom_status" } as never);
    const view = toPublicDecisionSchemaView(result);
    expect(view.gateDecision).toBe("unknown");
  });
});


describe("runtime status + bundle mapping", () => {
  it("normalizes runtime status fields with fallback", () => {
    const result = makeResponse({
      active_posture: "",
      backend: "gpt-5.3-mini",
      verify_status: undefined,
    } as never);
    const view = toRuntimeStatusView(result);
    expect(view).toEqual({
      activePosture: "n/a",
      backend: "gpt-5.3-mini",
      verifyStatus: "n/a",
    });
  });

  it("creates evidence bundle draft contract", () => {
    const result = makeResponse({
      request_id: "req-bundle",
      gate_decision: "hold",
      business_decision: "REVIEW_REQUIRED",
      next_action: "ROUTE_TO_HUMAN_REVIEW",
      required_evidence: ["approval_ticket"],
      missing_evidence: ["approval_ticket"],
      active_posture: "strict",
      backend: "gpt-5.3-mini",
      verify_status: "verified",
    } as never);

    const bundle = toEvidenceBundleDraft(result);
    expect(bundle.requestId).toBe("req-bundle");
    expect(bundle.businessDecision).toBe("REVIEW_REQUIRED");
    expect(bundle.runtimeStatus).toEqual({
      activePosture: "strict",
      backend: "gpt-5.3-mini",
      verifyStatus: "verified",
    });
  });
});
