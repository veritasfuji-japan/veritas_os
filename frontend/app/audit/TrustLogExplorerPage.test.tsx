import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import TrustLogExplorerPage from "./page";

const mockUseAuditData = vi.fn();

vi.mock("./hooks/useAuditData", () => ({
  useAuditData: () => mockUseAuditData(),
}));

vi.mock("../../components/i18n-provider", () => ({
  useI18n: () => ({
    t: (_ja: string, en: string) => en,
  }),
}));

vi.mock("@veritas/design-system", () => ({
  Card: ({ title, description, children }: { title?: string; description?: string; children: ReactNode }) => (
    <section>
      {title ? <h2>{title}</h2> : null}
      {description ? <p>{description}</p> : null}
      <div>{children}</div>
    </section>
  ),
}));

vi.mock("../../components/ui", () => ({
  StatusBadge: ({ label }: { label: string }) => <span>{label}</span>,
  ErrorBanner: ({ message }: { message: string }) => <div role="alert">{message}</div>,
}));

vi.mock("./components/SearchPanel", () => ({
  SearchPanel: () => <div>SearchPanel</div>,
}));
vi.mock("./components/AuditSummaryPanel", () => ({
  AuditSummaryPanel: () => <div>AuditSummaryPanel</div>,
}));
vi.mock("./components/AuditTimeline", () => ({
  AuditTimeline: () => <div>AuditTimeline</div>,
}));
vi.mock("./components/DetailPanel", () => ({
  DetailPanel: () => <div>DetailPanel</div>,
}));
vi.mock("./components/VerificationPanel", () => ({
  VerificationPanel: () => <div>VerificationPanel</div>,
}));
vi.mock("./components/ExportPanel", () => ({
  ExportPanel: () => <div>ExportPanel</div>,
}));

function createAuditDataMock(overrides: Record<string, unknown> = {}) {
  return {
    items: [],
    requestId: "",
    setRequestId: vi.fn(),
    requestResult: null,
    searchByRequestId: vi.fn().mockResolvedValue(undefined),
    crossSearch: { query: "", field: "all" },
    setCrossSearch: vi.fn(),
    filteredItems: [],
    loading: false,
    hasMore: false,
    cursor: null,
    loadLogs: vi.fn().mockResolvedValue(undefined),
    bindReceiptIdFromQuery: null,
    bindReceiptLookupLoading: false,
    bindReceiptLookupError: null,
    bindReceiptFoundInTimeline: false,
    bindReceiptLookupDetail: null,
    showBindReceiptFallback: false,
    error: null,
    auditSummary: null,
    stageFilter: "ALL",
    stageOptions: ["ALL"],
    selected: null,
    setStageFilter: vi.fn(),
    setSelected: vi.fn(),
    detailTab: "summary",
    setDetailTab: vi.fn(),
    selectedChain: null,
    previousEntry: null,
    nextEntry: null,
    decisionIds: [],
    selectedDecisionId: "",
    selectedDecisionEntry: null,
    verificationMessage: null,
    setSelectedDecisionId: vi.fn(),
    setVerificationMessage: vi.fn(),
    sortedItems: [],
    reportStartDate: "",
    reportEndDate: "",
    redactionMode: "none",
    exportFormat: "json",
    confirmPiiRisk: false,
    reportError: null,
    latestReport: null,
    exportTargetCount: 0,
    setReportStartDate: vi.fn(),
    setReportEndDate: vi.fn(),
    setRedactionMode: vi.fn(),
    setExportFormat: vi.fn(),
    setConfirmPiiRisk: vi.fn(),
    setReportError: vi.fn(),
    setLatestReport: vi.fn(),
    ...overrides,
  };
}

describe("TrustLogExplorerPage bind receipt fallback rendering", () => {
  beforeEach(() => {
    mockUseAuditData.mockReset();
  });

  it("Case A: hides fallback section when no bind_receipt_id query exists", () => {
    mockUseAuditData.mockReturnValue(createAuditDataMock());

    render(<TrustLogExplorerPage />);

    expect(screen.getByText("TrustLog Explorer")).toBeInTheDocument();
    expect(screen.queryByText("Bind Receipt Trace")).not.toBeInTheDocument();
    expect(screen.queryByText("Raw fallback detail")).not.toBeInTheDocument();
  });

  it("Case B: keeps fallback hidden when timeline hit is found", () => {
    mockUseAuditData.mockReturnValue(
      createAuditDataMock({
        bindReceiptIdFromQuery: "br-123",
        bindReceiptFoundInTimeline: true,
        showBindReceiptFallback: false,
      }),
    );

    render(<TrustLogExplorerPage />);

    expect(screen.getByText("Bind Receipt Trace")).toBeInTheDocument();
    expect(screen.getByText(/Matched audit log has been focused/i)).toBeInTheDocument();
    expect(screen.queryByText("Bind check summary")).not.toBeInTheDocument();
  });

  it("Case C: shows fallback details with required fields on timeline miss", () => {
    mockUseAuditData.mockReturnValue(
      createAuditDataMock({
        bindReceiptIdFromQuery: "br-404",
        bindReceiptFoundInTimeline: false,
        showBindReceiptFallback: true,
        bindReceiptLookupDetail: {
          bindReceiptId: "br-404",
          executionIntentId: "ei-200",
          finalOutcome: "BLOCKED",
          bindFailureReason: "authority_denied",
        },
      }),
    );

    render(<TrustLogExplorerPage />);

    expect(screen.getAllByText(/bind_receipt_id/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText("br-404").length).toBeGreaterThan(0);
    expect(screen.getByText(/execution_intent_id/i)).toBeInTheDocument();
    expect(screen.getByText("ei-200")).toBeInTheDocument();
    expect(screen.getByText(/final_outcome/i)).toBeInTheDocument();
    expect(screen.getByText("BLOCKED")).toBeInTheDocument();
    expect(screen.getAllByText(/bindFailureReason/i).length).toBeGreaterThan(0);
    expect(screen.getByText("authority_denied")).toBeInTheDocument();
  });

  it("Case D: shows compact bind check summary sections", () => {
    mockUseAuditData.mockReturnValue(
      createAuditDataMock({
        bindReceiptIdFromQuery: "br-404",
        bindReceiptFoundInTimeline: false,
        showBindReceiptFallback: true,
        bindReceiptLookupDetail: {
          bindReceiptId: "br-404",
          authorityCheckResult: { passed: false },
          constraintCheckResult: { result: "pass" },
          driftCheckResult: { passed: true },
          riskCheckResult: { result: "warn" },
        },
      }),
    );

    render(<TrustLogExplorerPage />);

    expect(screen.getByText("Bind check summary")).toBeInTheDocument();
    expect(screen.getByText("authorityCheckResult")).toBeInTheDocument();
    expect(screen.getByText("constraintCheckResult")).toBeInTheDocument();
    expect(screen.getByText("driftCheckResult")).toBeInTheDocument();
    expect(screen.getByText("riskCheckResult")).toBeInTheDocument();
  });

  it("Case E: exposes raw fallback detail disclosure entry", () => {
    mockUseAuditData.mockReturnValue(
      createAuditDataMock({
        bindReceiptIdFromQuery: "br-404",
        bindReceiptFoundInTimeline: false,
        showBindReceiptFallback: true,
        bindReceiptLookupDetail: {
          bindReceiptId: "br-404",
        },
      }),
    );

    render(<TrustLogExplorerPage />);

    expect(screen.getByText("Raw fallback detail")).toBeInTheDocument();
  });

  it("Case F: renders lookup error banner and keeps fallback hidden", () => {
    mockUseAuditData.mockReturnValue(
      createAuditDataMock({
        bindReceiptIdFromQuery: "br-500",
        bindReceiptLookupError: "lookup failed",
        showBindReceiptFallback: false,
      }),
    );

    render(<TrustLogExplorerPage />);

    expect(screen.getByRole("alert")).toHaveTextContent("lookup failed");
    expect(screen.queryByText("Bind check summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Raw fallback detail")).not.toBeInTheDocument();
  });
});
