import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const { loadMissionControlIngressPayloadMock } = vi.hoisted(() => ({
  loadMissionControlIngressPayloadMock: vi.fn(async () => null),
}));

vi.mock("./mission-control-ingress", () => ({
  loadMissionControlIngressPayload: loadMissionControlIngressPayloadMock,
}));

import CommandDashboardPage from "./page";

describe("CommandDashboardPage integration", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    loadMissionControlIngressPayloadMock.mockReset();
    loadMissionControlIngressPayloadMock.mockResolvedValue(null);
  });

  it("ignores searchParams e2e scenario in production-like environments", async () => {
    vi.stubEnv("NODE_ENV", "production");

    render(
      await CommandDashboardPage({
        searchParams: Promise.resolve({ e2e_governance_scenario: "main" }),
      }),
    );

    expect(loadMissionControlIngressPayloadMock).toHaveBeenCalledWith(null);
  });

  it("forwards searchParams e2e scenario only when e2e scenarios are enabled", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_ENABLE_E2E_SCENARIOS", "1");

    render(
      await CommandDashboardPage({
        searchParams: Promise.resolve({ e2e_governance_scenario: "fallback" }),
      }),
    );

    expect(loadMissionControlIngressPayloadMock).toHaveBeenCalledWith("fallback");
  });

  it("keeps page rendering behavior", async () => {
    vi.stubEnv("NODE_ENV", "production");

    render(await CommandDashboardPage());

    expect(screen.getByText("Live Event Feed")).toBeInTheDocument();
  });
});
