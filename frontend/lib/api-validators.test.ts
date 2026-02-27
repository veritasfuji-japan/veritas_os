import { describe, expect, it } from "vitest";

import {
  isGovernancePolicyResponse,
  isRequestLogResponse,
  isTrustLogsResponse,
  validateGovernancePolicyResponse,
} from "./api-validators";

const validGovernanceResponse = {
  ok: true,
  policy: {
    version: "governance_v1",
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
    risk_thresholds: {
      allow_upper: 0.4,
      warn_upper: 0.65,
      human_review_upper: 0.85,
      deny_upper: 1.0,
    },
    auto_stop: {
      enabled: true,
      max_risk_score: 0.85,
      max_consecutive_rejects: 5,
      max_requests_per_minute: 60,
    },
    log_retention: {
      retention_days: 90,
      audit_level: "full",
      include_fields: ["status", "risk"],
      redact_before_log: true,
      max_log_size: 10000,
    },
    updated_at: "2026-02-12T00:00:00Z",
    updated_by: "system",
  },
};

describe("api validators", () => {
  it("accepts valid governance policy response", () => {
    expect(isGovernancePolicyResponse(validGovernanceResponse)).toBe(true);
  });

  it("rejects malformed governance policy response", () => {
    expect(
      isGovernancePolicyResponse({
        ok: true,
        policy: {
          ...validGovernanceResponse.policy,
          updated_by: 123,
        },
      }),
    ).toBe(false);
  });

  it("classifies malformed governance response issues as semantic errors when values are invalid", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        updated_at: "12-02-2026",
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues[0].category).toBe("semantic");
    expect(validation.issues[0].path).toBe("policy.updated_at");
  });

  it("classifies threshold ordering violations as semantic errors", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        risk_thresholds: {
          allow_upper: 0.8,
          warn_upper: 0.6,
          human_review_upper: 0.85,
          deny_upper: 1,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.category === "semantic")).toBe(true);
  });

  it("rejects unsupported audit_level enum values", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        log_retention: {
          ...validGovernanceResponse.policy.log_retention,
          audit_level: "verbose",
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues[0].path).toBe("policy.log_retention.audit_level");
  });

  it("accepts valid trust logs response", () => {
    expect(
      isTrustLogsResponse({
        items: [{ request_id: "req-1", stage: "fuji", created_at: "2026-02-12T00:00:00Z" }],
        cursor: "0",
        next_cursor: "1",
        limit: 50,
        has_more: true,
      }),
    ).toBe(true);
  });

  it("rejects malformed trust logs response", () => {
    expect(
      isTrustLogsResponse({
        items: [{ request_id: 10 }],
        cursor: "0",
        next_cursor: "1",
        limit: 50,
        has_more: true,
      }),
    ).toBe(false);
  });

  it("accepts valid request log response", () => {
    expect(
      isRequestLogResponse({
        request_id: "req-1",
        items: [{ request_id: "req-1", stage: "planner" }],
        count: 1,
        chain_ok: true,
        verification_result: "ok",
      }),
    ).toBe(true);
  });

  it("rejects malformed request log response", () => {
    expect(
      isRequestLogResponse({
        request_id: "req-1",
        items: [],
        count: "1",
        chain_ok: true,
        verification_result: "ok",
      }),
    ).toBe(false);
  });
});
