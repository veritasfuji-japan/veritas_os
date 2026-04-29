import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CommandDashboardPage from "./page";

const loadMissionControlIngressPayloadMock = vi.fn();

vi.mock("./mission-control-ingress", () => ({
  loadMissionControlIngressPayload: () => loadMissionControlIngressPayloadMock(),
}));

describe("CommandDashboardPage", () => {
  beforeEach(() => {
    loadMissionControlIngressPayloadMock.mockReset();
  });

  it("renders dashboard content using backend-fed ingress payload", async () => {
    loadMissionControlIngressPayloadMock.mockResolvedValue({
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        bind_outcome: "ESCALATED",
      },
    });

    render(await CommandDashboardPage());

    expect(screen.getByText("コマンドダッシュボード")).toBeInTheDocument();
    expect(screen.getByText("decision_shaping")).toBeInTheDocument();
  });

  it("falls back to adapter render-safety snapshot when backend ingress is unavailable", async () => {
    loadMissionControlIngressPayloadMock.mockResolvedValue(null);

    render(await CommandDashboardPage());

    expect(screen.getByText("participatory")).toBeInTheDocument();
    expect(screen.getByText("BLOCKED")).toBeInTheDocument();
  });
});
