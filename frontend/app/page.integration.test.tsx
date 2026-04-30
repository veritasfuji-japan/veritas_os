import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CommandDashboardPage from "./page";

describe("CommandDashboardPage integration", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("resolves endpoint -> ingress -> container -> page main path", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        governance_layer_snapshot: {
          participation_state: "decision_shaping",
          preservation_state: "degrading",
          intervention_viability: "minimal",
          bind_outcome: "ESCALATED",
        },
      }),
    } as Response);

    render(await CommandDashboardPage());

    const fetchCalls = vi.mocked(globalThis.fetch).mock.calls;
    expect(
      fetchCalls.some(
        ([input, init]) =>
          input === "/api/veritas/v1/report/governance" &&
          (init as RequestInit | undefined)?.method === "GET" &&
          (init as RequestInit | undefined)?.cache === "no-store",
      ),
    ).toBe(true);
    expect(screen.getByText("decision_shaping")).toBeInTheDocument();
    expect(screen.getByText("degrading")).toBeInTheDocument();
    expect(screen.getByText("ESCALATED")).toBeInTheDocument();
  });

  it("keeps endpoint-unavailable fallback as safety path", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("network"));

    render(await CommandDashboardPage());

    expect(screen.getByText("participatory")).toBeInTheDocument();
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByText("BLOCKED")).toBeInTheDocument();
  });
});
