import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("/api/veritas/v1/report/governance", () => {
  it("does not return deterministic main payload from query when e2e scenarios are disabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?e2e_governance_scenario=main"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });

  it("does not return deterministic main payload from header when e2e scenarios are disabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance", {
      headers: { "x-veritas-e2e-governance-scenario": "main" },
    }));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });

  it("returns deterministic main scenario payload when e2e scenarios are explicitly enabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_ENABLE_E2E_SCENARIOS", "1");

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance", {
      headers: { "x-veritas-e2e-governance-scenario": "main" },
    }));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        bind_outcome: "ESCALATED",
      },
    });
  });

  it("returns deterministic fallback scenario payload in test environment", async () => {
    vi.stubEnv("NODE_ENV", "test");

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance?e2e_governance_scenario=fallback"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
        intervention_viability: "high",
        bind_outcome: "BLOCKED",
      },
    });
  });

  it("returns governance_layer_snapshot as backend-fed main path", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          governance_layer_snapshot: {
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            bind_outcome: "ESCALATED",
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        bind_outcome: "ESCALATED",
      },
    });
  });


  it("preserves enriched governance_layer_snapshot metadata fields", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          governance_layer_snapshot: {
            bind_outcome: "ESCALATED",
            bind_receipt_id: "br_123",
            execution_intent_id: "ei_123",
            bind_summary: { bind_outcome: "ESCALATED" },
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      governance_layer_snapshot: {
        bind_outcome: "ESCALATED",
        bind_receipt_id: "br_123",
        execution_intent_id: "ei_123",
        bind_summary: { bind_outcome: "ESCALATED" },
      },
    });
  });

  it("keeps compatibility with pre_bind_governance_snapshot payloads", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(
        JSON.stringify({
          pre_bind_governance_snapshot: {
            participation_state: "participatory",
            preservation_state: "open",
          },
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      ),
    );

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({
      pre_bind_governance_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
      },
    });
  });

  it("calls /v1/governance/live-snapshot when scenarios are not used", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ governance_layer_snapshot: { bind_outcome: "UNKNOWN" } }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );

    await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(fetchSpy).toHaveBeenCalledWith("http://internal-api:8000/v1/governance/live-snapshot", expect.any(Object));
  });

  it("returns unavailable when upstream live snapshot is unavailable", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 503 }));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });

});
