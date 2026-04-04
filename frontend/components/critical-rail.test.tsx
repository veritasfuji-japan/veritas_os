import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { CriticalRail } from "./critical-rail";
import type { CriticalRailMetric } from "./dashboard-types";

const items: CriticalRailMetric[] = [
  {
    key: "latency",
    label: "P99 Latency",
    severity: "healthy",
    currentValue: "120ms",
    baselineDelta: "+5ms",
    owner: "SRE",
    lastUpdated: "2025-01-01",
    openIncidents: 0,
    href: "/metrics/latency",
  },
  {
    key: "errors",
    label: "Error Rate",
    severity: "critical",
    currentValue: "4.2%",
    baselineDelta: "+3.8%",
    owner: "Backend",
    lastUpdated: "2025-01-01",
    openIncidents: 2,
    href: "/metrics/errors",
  },
];

describe("CriticalRail", () => {
  it("renders all items with labels and values", () => {
    render(<CriticalRail items={items} />);
    expect(screen.getByText("P99 Latency")).toBeInTheDocument();
    expect(screen.getByText("120ms")).toBeInTheDocument();
    expect(screen.getByText("Error Rate")).toBeInTheDocument();
    expect(screen.getByText("4.2%")).toBeInTheDocument();
  });

  it("renders severity badges", () => {
    render(<CriticalRail items={items} />);
    expect(screen.getByText("healthy")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
  });

  it("renders owner and incident info", () => {
    render(<CriticalRail items={items} />);
    expect(screen.getByText("Owner: SRE")).toBeInTheDocument();
    expect(screen.getByText("Open incidents: 2")).toBeInTheDocument();
  });

  it("has accessible section label", () => {
    render(<CriticalRail items={items} />);
    expect(screen.getByRole("region", { name: "critical rail" })).toBeInTheDocument();
  });
});
