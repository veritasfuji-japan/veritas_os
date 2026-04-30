import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("/api/veritas/v1/report/governance", () => {
  it("returns deterministic main scenario payload for frontend E2E header", async () => {
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


  it("returns deterministic fallback scenario payload for query parameter", async () => {
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

  it("returns 503 when upstream endpoint is unavailable", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    const response = await GET(new Request("http://localhost/api/veritas/v1/report/governance"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ error: "governance_feed_unavailable" });
  });
});
