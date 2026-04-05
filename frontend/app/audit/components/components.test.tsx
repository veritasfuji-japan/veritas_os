/* eslint-disable @typescript-eslint/no-explicit-any */
import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AuditSummaryPanel } from "./AuditSummaryPanel";
import { DetailPanel } from "./DetailPanel";
import { AuditTimeline } from "./AuditTimeline";
import { VerificationPanel } from "./VerificationPanel";
import { SearchPanel } from "./SearchPanel";
import { ExportPanel } from "./ExportPanel";

/* ------------------------------------------------------------------ */
/*  Mocks                                                              */
/* ------------------------------------------------------------------ */

vi.mock("../../../components/i18n-provider", () => ({
  useI18n: () => ({
    language: "en",
    t: (_ja: string, en: string) => en,
    tk: (k: string) => k,
    setLanguage: () => {},
  }),
}));

vi.mock("@veritas/design-system", () => ({
  Card: ({
    children,
    title,
  }: {
    children: React.ReactNode;
    title?: string;
  }) => (
    <div data-testid={`card-${title}`}>
      {title && <h3>{title}</h3>}
      {children}
    </div>
  ),
}));

vi.mock("../../../components/ui", () => ({
  StatCard: ({ label, value }: { label: string; value: number }) => (
    <div data-testid={`stat-${label}`}>{value}</div>
  ),
}));

vi.mock("../audit-types", async () => {
  const actual = await vi.importActual("../audit-types");
  return {
    ...actual,
    classifyChain: () => ({ status: "verified", reason: "ok" }),
  };
});

/* ------------------------------------------------------------------ */
/*  Shared mock data                                                   */
/* ------------------------------------------------------------------ */

const mockItem = {
  request_id: "req-001",
  decision_id: 42,
  sha256: "abc123hash",
  sha256_prev: "prevhash",
  created_at: "2026-01-01T00:00:00Z",
  stage: "retrieval",
  status: "ok",
  severity: "info",
  policy_version: "v1",
  replay_id: "replay-001",
  metadata: { key: "value" },
  continuation_claim_status: undefined,
};

const mockItem2 = {
  ...mockItem,
  request_id: "req-002",
  decision_id: 43,
  sha256: "def456hash",
  sha256_prev: "abc123hash",
  created_at: "2026-01-02T00:00:00Z",
  stage: "planner",
};

/* ================================================================== */
/*  AuditSummaryPanel                                                  */
/* ================================================================== */

describe("AuditSummaryPanel", () => {
  const baseSummary = {
    total: 10,
    verified: 7,
    broken: 1,
    missing: 1,
    orphan: 1,
    replayLinked: 3,
    policyVersions: { v1: 6, v2: 4 },
  };

  it("renders empty state when hasItems is false", () => {
    render(<AuditSummaryPanel summary={baseSummary} hasItems={false} />);
    expect(
      screen.getByText("Load logs to see the overall audit summary here."),
    ).toBeInTheDocument();
  });

  it("renders stat cards when hasItems is true", () => {
    render(<AuditSummaryPanel summary={baseSummary} hasItems />);
    expect(screen.getByTestId("stat-Total")).toHaveTextContent("10");
    expect(screen.getByTestId("stat-Verified")).toHaveTextContent("7");
    expect(screen.getByTestId("stat-Broken")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-Missing")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-Orphan")).toHaveTextContent("1");
    expect(screen.getByTestId("stat-Replay Linked")).toHaveTextContent("3");
  });

  it("renders policy version distribution", () => {
    render(<AuditSummaryPanel summary={baseSummary} hasItems />);
    expect(screen.getByText("Policy Version Distribution")).toBeInTheDocument();
    expect(screen.getByText("v1: 6")).toBeInTheDocument();
    expect(screen.getByText("v2: 4")).toBeInTheDocument();
  });

  it("renders integrity bar", () => {
    render(<AuditSummaryPanel summary={baseSummary} hasItems />);
    expect(screen.getByText(/Chain integrity/)).toBeInTheDocument();
    expect(screen.getByText(/70%/)).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  DetailPanel                                                        */
/* ================================================================== */

describe("DetailPanel", () => {
  const baseProps = {
    selected: null as typeof mockItem | null,
    selectedChain: null as { status: "verified"; reason: string } | null,
    previousEntry: null,
    nextEntry: null,
    detailTab: "summary" as const,
    onDetailTabChange: vi.fn(),
  };

  it("renders empty state when selected is null", () => {
    render(<DetailPanel {...baseProps} />);
    expect(
      screen.getByText(/Select a log from the timeline to see details/),
    ).toBeInTheDocument();
  });

  it("renders tab bar with 6 tabs when selected", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "hash chain match" }}
      />,
    );
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Metadata")).toBeInTheDocument();
    expect(screen.getByText("Hash")).toBeInTheDocument();
    expect(screen.getByText("Related")).toBeInTheDocument();
    expect(screen.getByText("Continuation")).toBeInTheDocument();
    expect(screen.getByText("Raw JSON")).toBeInTheDocument();
  });

  it("renders summary tab content with chain status", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "hash chain match" }}
      />,
    );
    expect(screen.getByText("VERIFIED")).toBeInTheDocument();
    expect(screen.getByText(/hash chain match/)).toBeInTheDocument();
  });

  it("switches to metadata tab on click", () => {
    const onDetailTabChange = vi.fn();
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "hash chain match" }}
        onDetailTabChange={onDetailTabChange}
      />,
    );
    fireEvent.click(screen.getByText("Metadata"));
    expect(onDetailTabChange).toHaveBeenCalledWith("metadata");
  });

  it("renders metadata tab content", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        detailTab="metadata"
      />,
    );
    expect(screen.getByText("Metadata Card")).toBeInTheDocument();
    expect(screen.getByText(/"key": "value"/)).toBeInTheDocument();
  });

  it("renders hash tab with previous/current/next entries", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        previousEntry={mockItem2 as any}
        nextEntry={mockItem2 as any}
        detailTab="hash"
      />,
    );
    expect(screen.getByText("Previous")).toBeInTheDocument();
    expect(screen.getByText("Current")).toBeInTheDocument();
    expect(screen.getByText("Next")).toBeInTheDocument();
  });

  it("renders hash tab with none when no adjacent entries", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        previousEntry={null}
        nextEntry={null}
        detailTab="hash"
      />,
    );
    const noneLabels = screen.getAllByText("none");
    expect(noneLabels).toHaveLength(2);
  });

  it("renders hash tab with chain broken warning", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "broken" as any, reason: "mismatch" }}
        detailTab="hash"
      />,
    );
    expect(screen.getByText(/Hash mismatch detected/)).toBeInTheDocument();
    expect(screen.getByText(/Reason.*mismatch/)).toBeInTheDocument();
  });

  it("renders hash tab with chain missing warning", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "missing" as any, reason: "hash absent" }}
        detailTab="hash"
      />,
    );
    expect(screen.getByText(/Hash missing/)).toBeInTheDocument();
  });

  it("renders hash tab with orphan warning", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "orphan" as any, reason: "no prev link" }}
        detailTab="hash"
      />,
    );
    expect(screen.getByText(/Orphan entry/)).toBeInTheDocument();
  });

  it("renders related IDs tab", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        detailTab="related"
      />,
    );
    expect(screen.getByText("request_id:")).toBeInTheDocument();
    expect(screen.getByText("req-001")).toBeInTheDocument();
    expect(screen.getByText("decision_id:")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("replay_id:")).toBeInTheDocument();
    expect(screen.getByText("replay-001")).toBeInTheDocument();
  });

  it("renders continuation tab with no-data message", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        detailTab="continuation"
      />,
    );
    expect(screen.getByText(/No continuation data/)).toBeInTheDocument();
  });

  it("renders continuation tab with full data", () => {
    const continuationItem = {
      ...mockItem,
      continuation_claim_status: "live",
      continuation_revalidation_status: "passed",
      continuation_revalidation_outcome: "accept",
      continuation_divergence_flag: false,
      continuation_should_refuse: false,
      continuation_reason_codes: ["R001", "R002"],
      continuation_law_version_id: "law-v1",
      continuation_support_basis_digest: "digest-abc",
      continuation_burden_headroom_digest: "burden-xyz",
      continuation_local_step_result: "pass",
    };
    render(
      <DetailPanel
        {...baseProps}
        selected={continuationItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        detailTab="continuation"
      />,
    );
    expect(screen.getByText("LIVE")).toBeInTheDocument();
    expect(screen.getByText("law-v1")).toBeInTheDocument();
    expect(screen.getByText("digest-abc")).toBeInTheDocument();
    expect(screen.getByText("burden-xyz")).toBeInTheDocument();
    expect(screen.getByText("passed")).toBeInTheDocument();
    expect(screen.getByText("accept")).toBeInTheDocument();
    expect(screen.getByText("pass")).toBeInTheDocument();
    expect(screen.getByText("R001, R002")).toBeInTheDocument();
  });

  it("renders continuation tab with divergence banner", () => {
    const divergedItem = {
      ...mockItem,
      continuation_claim_status: "narrowed",
      continuation_divergence_flag: true,
      continuation_should_refuse: true,
    };
    render(
      <DetailPanel
        {...baseProps}
        selected={divergedItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        detailTab="continuation"
      />,
    );
    expect(screen.getByText(/Step passed but chain-level continuation/)).toBeInTheDocument();
    expect(screen.getByText("NARROWED")).toBeInTheDocument();
    // Both shouldRefuse and divergenceFlag show YES
    const yesElements = screen.getAllByText("YES");
    expect(yesElements.length).toBeGreaterThanOrEqual(1);
  });

  it("renders raw JSON tab", () => {
    render(
      <DetailPanel
        {...baseProps}
        selected={mockItem as any}
        selectedChain={{ status: "verified", reason: "ok" }}
        detailTab="raw"
      />,
    );
    expect(screen.getByText("Expand JSON")).toBeInTheDocument();
    expect(screen.getByText(/"request_id": "req-001"/)).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  AuditTimeline                                                      */
/* ================================================================== */

describe("AuditTimeline", () => {
  const baseProps = {
    filteredItems: [] as any[],
    stageFilter: "all",
    stageOptions: ["all", "retrieval", "planner"],
    selected: null,
    onStageFilterChange: vi.fn(),
    onSelect: vi.fn(),
    onDetailTabChange: vi.fn(),
  };

  it("renders empty state when no items", () => {
    render(<AuditTimeline {...baseProps} />);
    expect(
      screen.getByText(/No logs loaded yet/),
    ).toBeInTheDocument();
  });

  it("renders stage filter select with options", () => {
    render(<AuditTimeline {...baseProps} />);
    const select = screen.getByLabelText("Stage");
    expect(select).toBeInTheDocument();
    expect(screen.getByText("all")).toBeInTheDocument();
    expect(screen.getByText("retrieval")).toBeInTheDocument();
    expect(screen.getByText("planner")).toBeInTheDocument();
  });

  it("renders timeline items with chain status", () => {
    render(
      <AuditTimeline
        {...baseProps}
        filteredItems={[mockItem as any, mockItem2 as any]}
      />,
    );
    // classifyChain is mocked to return "verified"
    const verifiedLabels = screen.getAllByText("verified");
    expect(verifiedLabels.length).toBeGreaterThanOrEqual(2);
  });

  it("calls onSelect when an item is clicked", () => {
    const onSelect = vi.fn();
    const onDetailTabChange = vi.fn();
    render(
      <AuditTimeline
        {...baseProps}
        filteredItems={[mockItem as any]}
        onSelect={onSelect}
        onDetailTabChange={onDetailTabChange}
      />,
    );
    // Click the timeline entry button
    const buttons = screen.getAllByRole("button");
    fireEvent.click(buttons[0]);
    expect(onSelect).toHaveBeenCalledWith(mockItem);
    expect(onDetailTabChange).toHaveBeenCalledWith("summary");
  });
});

/* ================================================================== */
/*  VerificationPanel                                                  */
/* ================================================================== */

describe("VerificationPanel", () => {
  const baseProps = {
    decisionIds: ["42", "43"],
    selectedDecisionId: "",
    selectedDecisionEntry: null,
    verificationMessage: null as string | null,
    onSelectedDecisionIdChange: vi.fn(),
    onVerify: vi.fn(),
  };

  it("renders decision ID dropdown and verify button", () => {
    render(<VerificationPanel {...baseProps} />);
    expect(
      screen.getByLabelText("Decision ID for verification"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Verify hash chain" }),
    ).toBeInTheDocument();
    // Options include placeholder + 2 IDs
    expect(screen.getByText("Select a decision ID")).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText("43")).toBeInTheDocument();
  });

  it("calls onVerify when button clicked", () => {
    const onVerify = vi.fn();
    render(<VerificationPanel {...baseProps} onVerify={onVerify} />);
    fireEvent.click(screen.getByRole("button", { name: "Verify hash chain" }));
    expect(onVerify).toHaveBeenCalledTimes(1);
  });

  it("renders verification message when provided", () => {
    render(
      <VerificationPanel
        {...baseProps}
        verificationMessage="All 5 entries verified."
      />,
    );
    expect(screen.getByText("All 5 entries verified.")).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  SearchPanel                                                        */
/* ================================================================== */

describe("SearchPanel", () => {
  const baseProps = {
    requestId: "",
    onRequestIdChange: vi.fn(),
    requestResult: null,
    onSearchByRequestId: vi.fn(),
    crossSearch: { query: "", field: "all" as const },
    onCrossSearchChange: vi.fn(),
    filteredCount: 0,
    loading: false,
    hasMore: false,
    cursor: null,
    onLoadLogs: vi.fn(),
  };

  it("renders load latest logs button", () => {
    render(<SearchPanel {...baseProps} />);
    expect(
      screen.getByRole("button", { name: "Load latest logs" }),
    ).toBeInTheDocument();
  });

  it("renders request ID search input", () => {
    render(<SearchPanel {...baseProps} />);
    expect(
      screen.getByLabelText("Search by request ID"),
    ).toBeInTheDocument();
  });

  it("calls onSearchByRequestId when search button clicked", () => {
    const onSearchByRequestId = vi.fn();
    render(
      <SearchPanel
        {...baseProps}
        onSearchByRequestId={onSearchByRequestId}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(onSearchByRequestId).toHaveBeenCalledTimes(1);
  });

  it("renders cross-search with field selector", () => {
    render(<SearchPanel {...baseProps} />);
    expect(screen.getByLabelText("Search field")).toBeInTheDocument();
    expect(screen.getByLabelText("cross-search")).toBeInTheDocument();
    // Verify field options
    expect(screen.getByText("All fields")).toBeInTheDocument();
    expect(screen.getByText("decision_id")).toBeInTheDocument();
    expect(screen.getByText("request_id")).toBeInTheDocument();
  });

  it("shows match count when cross-search query is present", () => {
    render(
      <SearchPanel
        {...baseProps}
        crossSearch={{ query: "req-001", field: "all" }}
        filteredCount={3}
      />,
    );
    expect(screen.getByText(/Matches.*3/)).toBeInTheDocument();
  });
});

/* ================================================================== */
/*  ExportPanel                                                        */
/* ================================================================== */

describe("ExportPanel", () => {
  const baseProps = {
    sortedItems: [mockItem as any],
    reportStartDate: "",
    reportEndDate: "",
    redactionMode: "full" as const,
    exportFormat: "json" as const,
    confirmPiiRisk: false,
    reportError: null as string | null,
    latestReport: null,
    exportTargetCount: 0,
    onReportStartDateChange: vi.fn(),
    onReportEndDateChange: vi.fn(),
    onRedactionModeChange: vi.fn(),
    onExportFormatChange: vi.fn(),
    onConfirmPiiRiskChange: vi.fn(),
    onReportError: vi.fn(),
    onLatestReport: vi.fn(),
  };

  it("renders date range inputs", () => {
    render(<ExportPanel {...baseProps} />);
    expect(
      screen.getByLabelText("Audit report start date"),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText("Audit report end date"),
    ).toBeInTheDocument();
  });

  it("renders redaction mode radio buttons", () => {
    render(<ExportPanel {...baseProps} />);
    expect(screen.getByLabelText("Full")).toBeInTheDocument();
    expect(screen.getByLabelText("Redacted")).toBeInTheDocument();
    expect(screen.getByLabelText("Metadata only")).toBeInTheDocument();
  });

  it("renders export format radio buttons (JSON/PDF)", () => {
    render(<ExportPanel {...baseProps} />);
    expect(screen.getByLabelText("JSON")).toBeInTheDocument();
    expect(screen.getByLabelText("PDF")).toBeInTheDocument();
  });

  it("renders PII warning checkbox", () => {
    render(<ExportPanel {...baseProps} />);
    expect(
      screen.getByLabelText("Acknowledge PII/metadata warning"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Security warning.*PII/),
    ).toBeInTheDocument();
  });

  it("shows error when export without PII confirmation", () => {
    const onReportError = vi.fn();
    render(
      <ExportPanel
        {...baseProps}
        reportStartDate="2026-01-01"
        reportEndDate="2026-01-31"
        confirmPiiRisk={false}
        onReportError={onReportError}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Generate JSON" }));
    expect(onReportError).toHaveBeenCalledWith(
      "Please acknowledge the PII/metadata warning.",
    );
  });

  it("shows export target count", () => {
    render(
      <ExportPanel
        {...baseProps}
        reportStartDate="2026-01-01"
        reportEndDate="2026-01-31"
        exportTargetCount={5}
      />,
    );
    expect(screen.getByText(/Export target.*5.*entries/)).toBeInTheDocument();
  });
});
