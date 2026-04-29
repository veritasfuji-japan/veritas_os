import { afterEach, describe, expect, it, vi } from "vitest";

import {
  loadMissionControlIngressPayload,
  mapGovernanceFeedToIngressPayload,
} from "./mission-control-ingress";

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

  it("returns null for unsupported payload shape", () => {
    expect(mapGovernanceFeedToIngressPayload({})).toBeNull();
  });
});

describe("loadMissionControlIngressPayload", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("returns mapped payload when backend feed is available", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        governance_layer_snapshot: {
          participation_state: "decision_shaping",
          preservation_state: "degrading",
        },
      }),
    } as Response);

    await expect(loadMissionControlIngressPayload()).resolves.toEqual({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
      },
    });
  });

  it("returns null when backend feed is unavailable", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    await expect(loadMissionControlIngressPayload()).resolves.toBeNull();
  });
});
