import { describe, expect, it } from "vitest";

import {
  isGovernancePolicyResponse,
  isRequestLogResponse,
  isTrustLogItem,
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

  it("rejects max_consecutive_rejects of zero (backend requires ge=1)", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        auto_stop: {
          ...validGovernanceResponse.policy.auto_stop,
          max_consecutive_rejects: 0,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.path === "policy.auto_stop.max_consecutive_rejects")).toBe(true);
  });

  it("rejects max_log_size below 100 (backend requires ge=100)", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        log_retention: {
          ...validGovernanceResponse.policy.log_retention,
          max_log_size: 50,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.path === "policy.log_retention.max_log_size")).toBe(true);
  });

  it("rejects max_consecutive_rejects above 1000 (backend requires le=1000)", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        auto_stop: {
          ...validGovernanceResponse.policy.auto_stop,
          max_consecutive_rejects: 1001,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.path === "policy.auto_stop.max_consecutive_rejects")).toBe(true);
  });

  it("rejects max_requests_per_minute above 10000 (backend requires le=10000)", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        auto_stop: {
          ...validGovernanceResponse.policy.auto_stop,
          max_requests_per_minute: 10001,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.path === "policy.auto_stop.max_requests_per_minute")).toBe(true);
  });

  it("rejects retention_days above 3650 (backend requires le=3650)", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        log_retention: {
          ...validGovernanceResponse.policy.log_retention,
          retention_days: 3651,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.path === "policy.log_retention.retention_days")).toBe(true);
  });

  it("rejects max_log_size above 1000000 (backend requires le=1000000)", () => {
    const validation = validateGovernancePolicyResponse({
      ok: true,
      policy: {
        ...validGovernanceResponse.policy,
        log_retention: {
          ...validGovernanceResponse.policy.log_retention,
          max_log_size: 1000001,
        },
      },
    });

    expect(validation.ok).toBe(false);
    if (validation.ok) {
      return;
    }

    expect(validation.issues.some((issue) => issue.path === "policy.log_retention.max_log_size")).toBe(true);
  });

  it("accepts valid trust logs response", () => {
    expect(
      isTrustLogsResponse({
        items: [
          {
            request_id: "req-1",
            created_at: "2026-02-12T00:00:00Z",
            sources: ["memory"],
            critics: [],
            checks: ["fuji"],
            approver: "system",
            sha256: "abc123",
          },
        ],
        cursor: "0",
        next_cursor: "1",
        limit: 50,
        has_more: true,
      }),
    ).toBe(true);
  });

  it("accepts trust log item with pipeline-provided fields (gate_status, gate_risk, query)", () => {
    expect(
      isTrustLogsResponse({
        items: [
          {
            request_id: "req-2",
            created_at: "2026-02-12T00:00:00Z",
            sources: ["web"],
            critics: [],
            checks: ["fuji"],
            approver: "system",
            sha256: "def456",
            query: "What is the risk?",
            gate_status: "allow",
            gate_risk: 0.15,
          },
        ],
        cursor: "0",
        next_cursor: null,
        limit: 50,
        has_more: false,
      }),
    ).toBe(true);
  });

  it("rejects trust log item missing required request_id", () => {
    expect(
      isTrustLogsResponse({
        items: [{ created_at: "2026-02-12T00:00:00Z" }],
        cursor: "0",
        next_cursor: "1",
        limit: 50,
        has_more: true,
      }),
    ).toBe(false);
  });

  it("rejects trust log item missing required created_at", () => {
    expect(
      isTrustLogsResponse({
        items: [{ request_id: "req-1" }],
        cursor: "0",
        next_cursor: "1",
        limit: 50,
        has_more: true,
      }),
    ).toBe(false);
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
        items: [{ request_id: "req-1", created_at: "2026-02-12T00:00:00Z", sources: [], critics: [], checks: [], approver: "system" }],
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

  it("rejects trust log item missing required sources (backend always provides default)", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        critics: [],
        checks: [],
        approver: "system",
      }),
    ).toBe(false);
  });

  it("rejects trust log item missing required critics (backend always provides default)", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        checks: [],
        approver: "system",
      }),
    ).toBe(false);
  });

  it("rejects trust log item missing required checks (backend always provides default)", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        approver: "system",
      }),
    ).toBe(false);
  });

  it("rejects trust log item missing required approver (backend defaults to 'system')", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        checks: [],
      }),
    ).toBe(false);
  });

  it("accepts trust log item with null sha256 fields (backend Optional[str])", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        checks: [],
        approver: "system",
        sha256: null,
        sha256_prev: null,
      }),
    ).toBe(true);
  });

  it("accepts trust log item with null pipeline fields (backend Optional types)", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        checks: [],
        approver: "system",
        query: null,
        gate_status: null,
        gate_risk: null,
      }),
    ).toBe(true);
  });

  it("rejects trust log item with invalid query type (backend Optional[str])", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        checks: [],
        approver: "system",
        query: 123,
      }),
    ).toBe(false);
  });

  it("rejects trust log item with invalid gate_status type (backend Optional[str])", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        checks: [],
        approver: "system",
        gate_status: true,
      }),
    ).toBe(false);
  });

  it("rejects trust log item with invalid gate_risk type (backend Optional[float])", () => {
    expect(
      isTrustLogItem({
        request_id: "req-1",
        created_at: "2026-02-12T00:00:00Z",
        sources: [],
        critics: [],
        checks: [],
        approver: "system",
        gate_risk: "high",
      }),
    ).toBe(false);
  });
});
