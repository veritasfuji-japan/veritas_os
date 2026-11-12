import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const headersGetMock = vi.fn<(name: string) => string | null>(() => null);
const readGovernanceFeed = vi.hoisted(() => vi.fn<(request: Request) => Promise<Response>>());

vi.mock("./api/veritas/v1/report/governance/route", () => ({ GET: readGovernanceFeed }));

vi.mock("next/headers", () => ({
  headers: async () => ({
    get: headersGetMock,
  }),
}));

import { mapGovernanceFeedToIngressPayload } from "../components/mission-governance-adapter";
import { loadMissionControlIngressPayload } from "./mission-control-ingress";

describe("mapGovernanceFeedToIngressPayload", () => {
  it("maps governance_layer_snapshot as main backend-fed path", () => {
    const result = mapGovernanceFeedToIngressPayload({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
      },
    });

    expect(result).toEqual({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
      },
    });
  });

  it("maps pre_bind_governance_snapshot as compatibility path", () => {
    const result = mapGovernanceFeedToIngressPayload({
      pre_bind_governance_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
      },
    });

    expect(result).toEqual({
      pre_bind_governance_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
      },
    });
  });



  it("maps governance demo phase snapshots without breaking main vocabulary", () => {
    const result = mapGovernanceFeedToIngressPayload({
      governance_layer_snapshot: {
        phase_snapshots: [{ phase_id: "pre_boundary_collapse_phase_1_open" }],
      },
    });

    expect(result).toEqual({
      governance_layer_snapshot: {
        phase_snapshots: [{ phase_id: "pre_boundary_collapse_phase_1_open" }],
      },
    });
  });

  it("returns null for unsupported payload shape", () => {
    expect(mapGovernanceFeedToIngressPayload({})).toBeNull();
  });






});

describe("loadMissionControlIngressPayload", () => {
  beforeEach(() => {
    headersGetMock.mockReset();
    headersGetMock.mockReturnValue(null);
    readGovernanceFeed.mockReset();
    readGovernanceFeed.mockImplementation(async () => Response.json({}));
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_ENABLE_E2E_SCENARIOS", "");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("passes request credentials to the shared handler and maps its payload", async () => {
    const inbound = new Headers({
      cookie: "__veritas_bff=session",
      authorization: "Bearer viewer",
      "x-forwarded-host": "external.invalid",
    });
    headersGetMock.mockImplementation((name) => inbound.get(name));
    const snapshot = { participation_state: "decision_shaping" };
    readGovernanceFeed.mockResolvedValue(Response.json({ governance_layer_snapshot: snapshot }));

    await expect(loadMissionControlIngressPayload()).resolves.toEqual({
      governance_layer_snapshot: snapshot,
    });
    const request = readGovernanceFeed.mock.calls[0]![0];
    expect(request.url).toBe("http://localhost/api/veritas/v1/report/governance");
    expect(request.headers.get("cookie")).toBe("__veritas_bff=session");
    expect(request.headers.get("authorization")).toBe("Bearer viewer");
    expect(request.headers.has("x-forwarded-host")).toBe(false);
  });

  it("ignores E2E scenarios when disabled", async () => {
    headersGetMock.mockImplementation((name) =>
      name === "x-veritas-e2e-governance-scenario" ? "main" : null);
    await loadMissionControlIngressPayload("main");
    await loadMissionControlIngressPayload();
    for (const [request] of readGovernanceFeed.mock.calls) {
      expect(new URL(request.url).search).toBe("");
    }
  });

  it("passes enabled E2E and demo overrides to the shared handler", async () => {
    vi.stubEnv("VERITAS_ENABLE_E2E_SCENARIOS", "1");
    await loadMissionControlIngressPayload("main", "pre_boundary_collapse");
    const query = new URL(readGovernanceFeed.mock.calls[0]![0].url).searchParams;
    expect(query.get("e2e_governance_scenario")).toBe("main");
    expect(query.get("demo_scenario")).toBe("pre_boundary_collapse");
  });

  it("returns no ingress when the shared handler rejects the request", async () => {
    readGovernanceFeed.mockResolvedValue(new Response(null, { status: 401 }));
    await expect(loadMissionControlIngressPayload()).resolves.toBeNull();
  });
});
