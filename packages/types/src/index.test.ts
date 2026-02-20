import { describe, expect, it } from "vitest";
import { isDecideResponse, isHealthResponse } from "./index";
import type { DecideResponse, HealthResponse } from "./index";

describe("types", () => {
  it("accepts a valid health response shape", () => {
    const response: HealthResponse = {
      status: "ok",
      service: "api",
      timestamp: "2026-01-01T00:00:00.000Z"
    };

    expect(response.status).toBe("ok");
  });

  it("validates health response payloads at runtime", () => {
    expect(
      isHealthResponse({
        status: "ok",
        service: "api",
        timestamp: "2026-01-01T00:00:00.000Z"
      })
    ).toBe(true);

    expect(
      isHealthResponse({
        status: "unknown",
        service: "api",
        timestamp: "2026-01-01T00:00:00.000Z"
      })
    ).toBe(false);
  });

  it("accepts a backend-aligned decide response shape", () => {
    const response: DecideResponse = {
      ok: true,
      error: null,
      request_id: "req_123",
      version: "veritas-api 1.x",
      chosen: { id: "alt-1" },
      alternatives: [
        {
          id: "alt-1",
          title: "Option A",
          description: "A description",
          score: 0.9
        }
      ],
      options: [
        {
          id: "alt-1",
          title: "Option A",
          description: "A description",
          score: 0.9
        }
      ],
      decision_status: "allow",
      rejection_reason: null,
      values: {
        scores: { safety: 0.9 },
        total: 0.9,
        top_factors: ["safety"],
        rationale: "safe"
      },
      telos_score: 0.8,
      fuji: { status: "allow" },
      gate: {
        risk: 0.1,
        telos_score: 0.8,
        decision_status: "allow",
        modifications: []
      },
      evidence: [
        {
          source: "memory",
          snippet: "evidence",
          confidence: 0.7
        }
      ],
      critique: [],
      debate: [],
      extras: {},
      plan: null,
      planner: null,
      persona: {},
      memory_citations: [],
      memory_used_count: 0,
      trust_log: null
    };

    expect(response.decision_status).toBe("allow");
  });

  it("validates decide response payloads at runtime", () => {
    const validPayload: DecideResponse = {
      ok: true,
      error: null,
      request_id: "req_123",
      version: "veritas-api 1.x",
      chosen: { id: "alt-1" },
      alternatives: [],
      options: [],
      decision_status: "allow",
      rejection_reason: null,
      values: null,
      telos_score: 0.8,
      fuji: {},
      gate: {
        risk: 0.1,
        telos_score: 0.8,
        decision_status: "allow",
        modifications: []
      },
      evidence: [],
      critique: [],
      debate: [],
      extras: {},
      plan: null,
      planner: null,
      persona: {},
      memory_citations: [],
      memory_used_count: 0,
      trust_log: null
    };

    expect(isDecideResponse(validPayload)).toBe(true);

    expect(
      isDecideResponse({
        ...validPayload,
        decision_status: "unknown"
      })
    ).toBe(false);
  });
});
