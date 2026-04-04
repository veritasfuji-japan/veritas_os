import { describe, it, expect } from "vitest";
import {
  FUJI_LABELS,
  MODE_EXPLANATIONS,
  ROLE_CAPABILITIES,
  DIFF_CATEGORY_LABELS,
  APPROVAL_STATUS_ACCENT,
} from "./constants";

describe("governance constants", () => {
  it("FUJI_LABELS covers all expected rule keys", () => {
    const keys = Object.keys(FUJI_LABELS);
    expect(keys).toContain("pii_check");
    expect(keys).toContain("self_harm_block");
    expect(keys).toContain("llm_safety_head");
    expect(keys.length).toBe(8);
  });

  it("MODE_EXPLANATIONS has standard and eu_ai_act", () => {
    expect(MODE_EXPLANATIONS.standard.summary).toBeTruthy();
    expect(MODE_EXPLANATIONS.eu_ai_act.summary).toBeTruthy();
    expect(MODE_EXPLANATIONS.eu_ai_act.affects.length).toBeGreaterThan(0);
  });

  it("ROLE_CAPABILITIES covers viewer, operator, admin", () => {
    expect(ROLE_CAPABILITIES.viewer.permissions.length).toBeGreaterThan(0);
    expect(ROLE_CAPABILITIES.operator.permissions.length).toBeGreaterThan(0);
    expect(ROLE_CAPABILITIES.admin.permissions.length).toBeGreaterThan(0);
  });

  it("DIFF_CATEGORY_LABELS covers all categories", () => {
    const cats = ["rule", "threshold", "escalation", "retention", "rollout", "approval", "meta"] as const;
    for (const cat of cats) {
      expect(DIFF_CATEGORY_LABELS[cat]).toBeTruthy();
    }
  });

  it("APPROVAL_STATUS_ACCENT maps statuses to accent types", () => {
    expect(APPROVAL_STATUS_ACCENT.approved).toBe("success");
    expect(APPROVAL_STATUS_ACCENT.pending).toBe("warning");
    expect(APPROVAL_STATUS_ACCENT.rejected).toBe("danger");
    expect(APPROVAL_STATUS_ACCENT.draft).toBe("info");
  });
});
