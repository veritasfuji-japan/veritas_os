import { describe, it, expect } from "vitest";
import {
  bumpDraftVersion,
  collectChanges,
  deepEqual,
  getDefaultDriftScoringConfig,
  getDefaultOperatorVerbosity,
  getDefaultPsidConfig,
  getDefaultRevocationConfig,
  getDefaultShadowValidationConfig,
  getDefaultWatConfig,
  isRecordObject,
  normalizeGovernancePolicyWatFields,
} from "./helpers";

describe("isRecordObject", () => {
  it("returns true for plain objects", () => {
    expect(isRecordObject({ key: "value" })).toBe(true);
  });

  it("returns false for null and arrays", () => {
    expect(isRecordObject(null)).toBe(false);
    expect(isRecordObject(["a"])).toBe(false);
  });
});

describe("deepEqual", () => {
  it("returns true for identical primitives", () => {
    expect(deepEqual(1, 1)).toBe(true);
    expect(deepEqual("a", "a")).toBe(true);
    expect(deepEqual(null, null)).toBe(true);
  });

  it("returns false for different primitives", () => {
    expect(deepEqual(1, 2)).toBe(false);
    expect(deepEqual("a", "b")).toBe(false);
  });

  it("returns false when types differ", () => {
    expect(deepEqual(1, "1")).toBe(false);
    expect(deepEqual(null, undefined)).toBe(false);
  });

  it("compares arrays deeply", () => {
    expect(deepEqual([1, 2], [1, 2])).toBe(true);
    expect(deepEqual([1, 2], [1, 3])).toBe(false);
    expect(deepEqual([1], [1, 2])).toBe(false);
  });

  it("compares nested objects deeply", () => {
    expect(deepEqual({ a: { b: 1 } }, { a: { b: 1 } })).toBe(true);
    expect(deepEqual({ a: { b: 1 } }, { a: { b: 2 } })).toBe(false);
  });

  it("returns false for array vs object", () => {
    expect(deepEqual([1], { 0: 1 })).toBe(false);
  });
});

describe("collectChanges", () => {
  it("detects added and changed keys", () => {
    const changes = collectChanges("", { a: 1 }, { a: 2, b: 3 });
    expect(changes).toHaveLength(2);
    expect(changes[0]).toMatchObject({ path: "a", old: "1", next: "2" });
    expect(changes[1]).toMatchObject({ path: "b", next: "3" });
  });

  it("categorizes paths correctly", () => {
    const changes = collectChanges("", { fuji_rules: 1 }, { fuji_rules: 2 });
    expect(changes[0].category).toBe("rule");
  });

  it("returns empty when objects are equal", () => {
    expect(collectChanges("", { a: 1 }, { a: 1 })).toHaveLength(0);
  });
});

describe("bumpDraftVersion", () => {
  it("increments trailing number and appends -draft", () => {
    expect(bumpDraftVersion("1.0.3")).toBe("1.0.4-draft");
  });

  it("appends -draft.1 when version has no trailing number pattern", () => {
    expect(bumpDraftVersion("alpha")).toBe("alpha-draft.1");
  });
});

describe("normalizeGovernancePolicyWatFields", () => {
  it("returns defaults when schema sections are missing", () => {
    const normalized = normalizeGovernancePolicyWatFields({
      version: "v1",
      updated_at: "2026-01-01T00:00:00Z",
      updated_by: "system",
      fuji_rules: {
        pii_check: true,
        self_harm_block: true,
        illicit_block: true,
        violence_review: true,
        minors_review: true,
        keyword_hard_block: true,
        keyword_soft_flag: true,
        llm_safety_head: true,
      },
      risk_thresholds: { allow_upper: 0.3, warn_upper: 0.5, human_review_upper: 0.7, deny_upper: 1 },
      auto_stop: { enabled: true, max_risk_score: 0.9, max_consecutive_rejects: 3, max_requests_per_minute: 10 },
      log_retention: { retention_days: 30, audit_level: "full", include_fields: [], redact_before_log: true, max_log_size: 1000 },
      rollout_controls: { strategy: "disabled", canary_percent: 0, stage: 0, staged_enforcement: false },
      approval_workflow: { human_review_ticket: "", human_review_required: false, approver_identity_binding: true, approver_identities: [] },
      approval_status: "pending",
    } as never);
    expect(normalized.wat).toEqual(getDefaultWatConfig());
    expect(normalized.psid).toEqual(getDefaultPsidConfig());
    expect(normalized.shadow_validation).toEqual(getDefaultShadowValidationConfig());
    expect(normalized.revocation).toEqual(getDefaultRevocationConfig());
    expect(normalized.drift_scoring).toEqual(getDefaultDriftScoringConfig());
    expect(normalized.operator_verbosity).toBe(getDefaultOperatorVerbosity());
  });

  it("normalizes malformed enums to backend-supported values", () => {
    const normalized = normalizeGovernancePolicyWatFields({
      wat: { issuance_mode: "hybrid" },
      shadow_validation: { partial_validation_default: true },
      revocation: { mode: "soft" },
    } as never);

    expect(normalized.wat.issuance_mode).toBe("shadow_only");
    expect(normalized.shadow_validation.partial_validation_default).toBe("non_admissible");
    expect(normalized.revocation.mode).toBe("bounded_eventual_consistency");
  });
});
