import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "./i18n-provider";
import { MissionPage } from "./mission-page";

describe("MissionPage", () => {
  it("renders enhanced critical rail and global health summary", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Global Health Summary")).toBeInTheDocument();
    expect(screen.getByText("Current band:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Critical Rail")).toBeInTheDocument();
    expect(screen.getByText("FUJI reject")).toBeInTheDocument();
    expect(screen.getByText("Open incidents: 4")).toBeInTheDocument();
  });

  it("renders action-oriented priority cards", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getAllByText(/Why now/)).toHaveLength(3);
    expect(screen.getAllByText(/Impact window/)).toHaveLength(3);
    expect(screen.getByRole("link", { name: "Decision で triage" })).toHaveAttribute("href", "/console");
  });

  it("surfaces trust-chain, governance, and evidence routing context", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Trust Chain Integrity")).toBeInTheDocument();
    expect(screen.getByText("Verification:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Governance approval risk")).toBeInTheDocument();
    expect(screen.getByText("Risk → Decision → Evidence → Report")).toBeInTheDocument();
    expect(screen.getByText("/health security posture (mandatory)")).toBeInTheDocument();
    expect(screen.getByText("Encryption algorithm:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Authentication mode:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Direct FUJI API:", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("degraded:", { exact: false })).toBeInTheDocument();
  });

  it("renders pre-bind governance vocabulary and bind separation", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            intervention_viability: "minimal",
            concise_rationale: "early warning signal indicates reduced intervention headroom.",
            bind_outcome: "ESCALATED",
          }}
        />
      </I18nProvider>,
    );

    expect(screen.getByText(/Governance layer timeline/)).toBeInTheDocument();
    expect(screen.getByText(/participation_state:/)).toBeInTheDocument();
    expect(screen.getByText("decision_shaping")).toBeInTheDocument();
    expect(screen.getByText(/preservation_state:/)).toBeInTheDocument();
    expect(screen.getByText("degrading")).toBeInTheDocument();
    expect(screen.getByText(/intervention_viability:/)).toBeInTheDocument();
    expect(screen.getByText("minimal")).toBeInTheDocument();
    expect(screen.getByText(/bind_outcome:/)).toBeInTheDocument();
    expect(screen.getByText("ESCALATED")).toBeInTheDocument();
    expect(screen.getByText(/concise_rationale:/)).toBeInTheDocument();
  });

  it("omits governance timeline when additive pre-bind fields are absent", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
          governanceLayerSnapshot={{ bind_outcome: "COMMITTED" }}
        />
      </I18nProvider>,
    );

    expect(screen.queryByText(/Governance layer timeline/)).not.toBeInTheDocument();
    expect(screen.queryByText(/participation_state:/)).not.toBeInTheDocument();
  });
});
