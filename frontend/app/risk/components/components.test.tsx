import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import React from "react";

import type { RiskPoint, FlaggedEntry, TrendBucket } from "../risk-types";

vi.mock("../../../components/i18n-provider", () => ({
  useI18n: () => ({ language: "en", t: (_ja: string, en: string) => en, tk: (k: string) => k, setLanguage: () => {} }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock("../data-helpers", async () => {
  const actual = await vi.importActual("../data-helpers");
  return {
    ...actual,
    getCluster: () => "critical",
    pointFill: () => "#ff0000",
    bucketMeaning: () => "test meaning",
  };
});

import { DrilldownPanel } from "./DrilldownPanel";
import { FlaggedRequestsList } from "./FlaggedRequestsList";
import { InsightCards } from "./InsightCards";
import { RiskScatterPlot } from "./RiskScatterPlot";
import { TrendChart } from "./TrendChart";
import { WhyFlaggedPanel } from "./WhyFlaggedPanel";

const mockPoint: RiskPoint = { id: "req-001", uncertainty: 0.8, risk: 0.9, timestamp: Date.now() };

const mockEntry: FlaggedEntry = {
  point: mockPoint,
  cluster: "critical",
  severity: "critical",
  status: "new",
  reason: {
    policyConfidence: 0.2,
    unstableOutputSignal: true,
    retrievalAnomaly: false,
    summary: "High risk detected",
    suggestedAction: "Review immediately",
  },
  relatedPolicyHits: ["PII detected"],
  stageAnomalies: ["Latency spike"],
};

/* ------------------------------------------------------------------ */
/*  DrilldownPanel                                                     */
/* ------------------------------------------------------------------ */
describe("DrilldownPanel", () => {
  it("renders empty state when entry is null", () => {
    render(<DrilldownPanel entry={null} />);
    expect(screen.getByTestId("empty-drilldown")).toBeInTheDocument();
  });

  it("renders entry details", () => {
    render(<DrilldownPanel entry={mockEntry} />);
    expect(screen.getByText("req-001")).toBeInTheDocument();
    expect(screen.getByText("0.800")).toBeInTheDocument();
    expect(screen.getByText("0.900")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText(/PII detected/)).toBeInTheDocument();
    expect(screen.getByText(/Latency spike/)).toBeInTheDocument();
  });

  it("renders navigation links", () => {
    render(<DrilldownPanel entry={mockEntry} />);
    expect(screen.getByText("Open in Decision")).toHaveAttribute("href", "/console?request_id=req-001");
    expect(screen.getByText("Open in TrustLog")).toHaveAttribute("href", "/audit?request_id=req-001");
    expect(screen.getByText("Adjust in Governance")).toHaveAttribute("href", "/governance");
  });
});

/* ------------------------------------------------------------------ */
/*  FlaggedRequestsList                                                */
/* ------------------------------------------------------------------ */
describe("FlaggedRequestsList", () => {
  it("renders empty state when entries is empty", () => {
    render(<FlaggedRequestsList entries={[]} selectedPointId={null} onSelectPoint={() => {}} />);
    expect(screen.getByTestId("empty-flagged")).toBeInTheDocument();
  });

  it("renders entries with IDs, severity badges, and links", () => {
    render(<FlaggedRequestsList entries={[mockEntry]} selectedPointId={null} onSelectPoint={() => {}} />);
    expect(screen.getByText("req-001")).toBeInTheDocument();
    expect(screen.getByText("critical")).toBeInTheDocument();
    expect(screen.getByText("Open in Decision")).toHaveAttribute("href", "/console?request_id=req-001");
    expect(screen.getByText("Open in TrustLog")).toHaveAttribute("href", "/audit?request_id=req-001");
  });

  it("calls onSelectPoint when entry button clicked", () => {
    const onSelect = vi.fn();
    render(<FlaggedRequestsList entries={[mockEntry]} selectedPointId={null} onSelectPoint={onSelect} />);
    fireEvent.click(screen.getByRole("button"));
    expect(onSelect).toHaveBeenCalledWith("req-001");
  });
});

/* ------------------------------------------------------------------ */
/*  InsightCards                                                        */
/* ------------------------------------------------------------------ */
describe("InsightCards", () => {
  const baseProps = {
    clusterRatio: 0.02,
    clusterCount: 3,
    filteredPointsCount: 100,
    unsafeBurst: false,
    latestHighRisk: 2,
    uncertainCount: 5,
  };

  it("renders 3 cards with correct text", () => {
    render(<InsightCards {...baseProps} />);
    expect(screen.getByText("Policy drift")).toBeInTheDocument();
    expect(screen.getByText("Unsafe burst")).toBeInTheDocument();
    expect(screen.getByText("Unstable output cluster")).toBeInTheDocument();
  });

  it("applies warning styling when clusterRatio >= 0.05", () => {
    const { container } = render(<InsightCards {...baseProps} clusterRatio={0.06} />);
    const policyCard = container.querySelector(".border-warning\\/40");
    expect(policyCard).toBeInTheDocument();
  });

  it("applies danger styling when unsafeBurst is true", () => {
    const { container } = render(<InsightCards {...baseProps} unsafeBurst={true} />);
    const burstCard = container.querySelector(".border-danger\\/40");
    expect(burstCard).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  RiskScatterPlot                                                    */
/* ------------------------------------------------------------------ */
describe("RiskScatterPlot", () => {
  const baseProps = {
    filteredPoints: [mockPoint],
    selectedPointId: null,
    hoveredPointId: null,
    hoveredPoint: null,
    onSelectPoint: vi.fn(),
    onHoverPoint: vi.fn(),
  };

  it("renders SVG with scatter points", () => {
    render(<RiskScatterPlot {...baseProps} />);
    const svg = screen.getByRole("img");
    expect(svg).toBeInTheDocument();
    const buttons = screen.getAllByRole("button");
    expect(buttons.length).toBeGreaterThanOrEqual(1);
  });

  it("renders hover summary when hoveredPoint is provided", () => {
    render(<RiskScatterPlot {...baseProps} hoveredPoint={mockPoint} hoveredPointId={mockPoint.id} />);
    expect(screen.getByTestId("hover-summary")).toBeInTheDocument();
    expect(screen.getByText("req-001")).toBeInTheDocument();
  });
});

/* ------------------------------------------------------------------ */
/*  TrendChart                                                         */
/* ------------------------------------------------------------------ */
describe("TrendChart", () => {
  const mockBuckets: TrendBucket[] = [
    { label: "0-3h", total: 10, highRisk: 0 },
    { label: "3-6h", total: 15, highRisk: 2 },
  ];

  const baseProps = {
    trend: mockBuckets,
    spikeDetected: false,
    unsafeBurst: false,
    onSelectCluster: vi.fn(),
  };

  it("renders trend buckets", () => {
    render(<TrendChart {...baseProps} />);
    expect(screen.getByText("0-3h")).toBeInTheDocument();
    expect(screen.getByText("3-6h")).toBeInTheDocument();
  });

  it("shows spike detected message when spikeDetected is true", () => {
    render(<TrendChart {...baseProps} spikeDetected={true} />);
    expect(screen.getByText(/Spike detected/)).toBeInTheDocument();
  });

  it("shows burst message when unsafeBurst is true", () => {
    render(<TrendChart {...baseProps} unsafeBurst={true} />);
    expect(screen.getByText(/Unsafe burst active/)).toBeInTheDocument();
  });

  it("calls onSelectCluster when a bucket is clicked", () => {
    const onSelect = vi.fn();
    render(<TrendChart {...baseProps} onSelectCluster={onSelect} />);
    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[0]);
    expect(onSelect).toHaveBeenCalledWith("all");
    fireEvent.click(buttons[1]);
    expect(onSelect).toHaveBeenCalledWith("critical");
  });
});

/* ------------------------------------------------------------------ */
/*  WhyFlaggedPanel                                                    */
/* ------------------------------------------------------------------ */
describe("WhyFlaggedPanel", () => {
  it("renders empty state when entry is null", () => {
    render(<WhyFlaggedPanel entry={null} />);
    expect(screen.getByTestId("empty-why-flagged")).toBeInTheDocument();
  });

  it("renders flag reason details", () => {
    render(<WhyFlaggedPanel entry={mockEntry} />);
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.getByText("Detected")).toBeInTheDocument();
    expect(screen.getByText("Normal")).toBeInTheDocument();
  });

  it("renders analysis summary and suggested action", () => {
    render(<WhyFlaggedPanel entry={mockEntry} />);
    expect(screen.getByText("High risk detected")).toBeInTheDocument();
    expect(screen.getByText("Review immediately")).toBeInTheDocument();
  });
});
