import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MissionPage } from "./mission-page";
import { I18nProvider } from "./i18n-provider";

describe("MissionPage", () => {
  it("renders critical rail items and operational priorities", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("Critical Rail")).toBeInTheDocument();
    expect(screen.getByText("FUJI reject")).toBeInTheDocument();
    expect(screen.getByText("Replay mismatch")).toBeInTheDocument();
    expect(screen.getByText("policy update")).toBeInTheDocument();
    expect(screen.getByText("broken chain")).toBeInTheDocument();
    expect(screen.getByText("risk burst")).toBeInTheDocument();
    expect(screen.getByText(/#1 最優先/)).toBeInTheDocument();
  });

  it("renders system health states", () => {
    render(
      <I18nProvider>
        <MissionPage
          title="Command Dashboard"
          subtitle="Mission overview"
          chips={["Uptime Lattice", "Signal Watch", "Anomaly Queue"]}
        />
      </I18nProvider>,
    );

    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("degraded")).toBeInTheDocument();
    expect(screen.getByText("health")).toBeInTheDocument();
  });
});
