import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "./i18n-provider";
import { MissionControlContainer } from "./mission-control-container";

afterEach(() => vi.restoreAllMocks());

describe("MissionControlContainer", () => {
  it("renders timeline using live ingress payload", () => {
    render(
      <I18nProvider>
        <MissionControlContainer
          ingressPayload={{
            governance_layer_snapshot: {
              participation_state: "decision_shaping",
              preservation_state: "degrading",
              intervention_viability: "minimal",
              bind_outcome: "ESCALATED",
            },
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("decision_shaping")).toBeInTheDocument();
    expect(screen.getByText("degrading")).toBeInTheDocument();
    expect(screen.getByText("ESCALATED")).toBeInTheDocument();
  });

  it("loads the same-origin feed in the browser when server ingress is unavailable", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      Response.json({ governance_layer_snapshot: { participation_state: "decision_shaping" } }),
    );
    render(
      <I18nProvider>
        <MissionControlContainer ingressPayload={null} />
      </I18nProvider>,
    );

    expect(await screen.findByText("decision_shaping")).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/veritas/v1/report/governance",
      expect.objectContaining({ credentials: "same-origin", cache: "no-store" }),
    );
  });

  it("uses safety fallback when ingress payload is absent", () => {
    render(
      <I18nProvider>
        <MissionControlContainer />
      </I18nProvider>,
    );

    expect(screen.getByText("participatory")).toBeInTheDocument();
    expect(screen.getByText("open")).toBeInTheDocument();
    expect(screen.getByText("BLOCKED")).toBeInTheDocument();
  });
});
