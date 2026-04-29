import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "./i18n-provider";
import { MissionControlContainer } from "./mission-control-container";

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
