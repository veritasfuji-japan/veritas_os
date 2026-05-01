import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("../../../components/i18n-provider", () => ({
  useI18n: () => ({
    language: "en",
    t: (_ja: string, en: string) => en,
    tk: (k: string) => k,
    setLanguage: () => {},
  }),
}));

const mockFetch = vi.fn();
vi.mock("../../../lib/api-client", () => ({
  veritasFetch: (...args: unknown[]) => mockFetch(...args),
}));

vi.mock("@veritas/types", async () => {
  const actual = await vi.importActual("@veritas/types");
  return {
    ...actual,
    isTrustLogsResponse: (payload: unknown) => {
      if (!payload || typeof payload !== "object") return false;
      return "items" in payload;
    },
    isRequestLogResponse: (payload: unknown) => {
      if (!payload || typeof payload !== "object") return false;
      return "items" in payload;
    },
  };
});

vi.mock("../audit-types", async () => {
  const actual = await vi.importActual("../audit-types");
  return {
    ...actual,
    classifyChain: () => ({ status: "verified", reason: "ok" }),
    computeAuditSummary: () => ({
      total: 0,
      verified: 0,
      broken: 0,
      missing: 0,
      orphan: 0,
      policyVersions: [],
    }),
  };
});

import { useAuditData } from "./useAuditData";

const MOCK_ITEMS = [
  {
    request_id: "req-001",
    decision_id: "42",
    sha256: "abc123",
    sha256_prev: "prev123",
    created_at: "2026-01-02T00:00:00Z",
    stage: "retrieval",
    status: "ok",
    severity: "info",
    policy_version: "v1",
  },
  {
    request_id: "req-002",
    decision_id: "43",
    sha256: "def456",
    sha256_prev: "abc123",
    created_at: "2026-01-01T00:00:00Z",
    stage: "generation",
    status: "ok",
    severity: "info",
    policy_version: "v1",
  },
];

describe("useAuditData", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    window.history.replaceState({}, "", "/audit");
  });

  it("initialises with correct defaults", () => {
    const { result } = renderHook(() => useAuditData());
    expect(result.current.items).toEqual([]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
    expect(result.current.stageFilter).toBe("ALL");
    expect(result.current.detailTab).toBe("summary");
  });

  it("loadLogs fetches and stores items", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: "cursor-1", has_more: true }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    expect(result.current.items).toHaveLength(2);
    expect(result.current.hasMore).toBe(true);
    expect(result.current.cursor).toBe("cursor-1");
  });

  it("loadLogs appends items when replace is false", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });
    expect(result.current.items).toHaveLength(2);

    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: [{ ...MOCK_ITEMS[0], request_id: "req-003" }], next_cursor: null, has_more: false }),
    });

    await act(async () => {
      await result.current.loadLogs("cursor-1", false);
    });
    expect(result.current.items).toHaveLength(3);
  });

  it("loadLogs handles HTTP error", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500 });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });
    expect(result.current.error).toContain("HTTP 500");
  });

  it("loadLogs handles invalid response format", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ unexpected: "data" }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });
    expect(result.current.error).toContain("format error");
  });

  it("loadLogs handles network error", async () => {
    mockFetch.mockRejectedValue(new Error("Network failure"));

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });
    expect(result.current.error).toContain("Network error");
  });

  it("sortedItems sorts by created_at descending", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    expect(result.current.sortedItems[0].request_id).toBe("req-001");
    expect(result.current.sortedItems[1].request_id).toBe("req-002");
  });

  it("stageOptions derive from loaded items", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    expect(result.current.stageOptions).toContain("ALL");
    expect(result.current.stageOptions).toContain("retrieval");
    expect(result.current.stageOptions).toContain("generation");
  });

  it("filteredItems filters by stageFilter", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    act(() => { result.current.setStageFilter("retrieval"); });
    expect(result.current.filteredItems).toHaveLength(1);
    expect(result.current.filteredItems[0].request_id).toBe("req-001");
  });

  it("crossSearch filters items", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    act(() => {
      result.current.setCrossSearch({ query: "req-001", field: "request_id" });
    });
    expect(result.current.filteredItems).toHaveLength(1);
  });

  it("searchByRequestId requires non-empty input", async () => {
    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.searchByRequestId();
    });
    expect(result.current.error).toContain("enter request_id");
  });

  it("decisionIds derive from loaded items", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    expect(result.current.decisionIds).toContain("42");
    expect(result.current.decisionIds).toContain("43");
  });

  it("state setters work correctly", () => {
    const { result } = renderHook(() => useAuditData());

    act(() => { result.current.setDetailTab("metadata"); });
    expect(result.current.detailTab).toBe("metadata");

    act(() => { result.current.setRedactionMode("redacted"); });
    expect(result.current.redactionMode).toBe("redacted");

    act(() => { result.current.setExportFormat("pdf"); });
    expect(result.current.exportFormat).toBe("pdf");

    act(() => { result.current.setConfirmPiiRisk(true); });
    expect(result.current.confirmPiiRisk).toBe(true);
  });

  it("keeps legacy behaviour when bind_receipt_id query is absent", () => {
    const { result } = renderHook(() => useAuditData());
    expect(result.current.bindReceiptIdFromQuery).toBeNull();
    expect(result.current.bindReceiptLookupError).toBeNull();
    expect(result.current.bindReceiptLookupDetail).toBeNull();
    expect(result.current.showBindReceiptFallback).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("loads bind receipt from query param and then loads trust logs", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=br-001");
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            ok: true,
            bind_receipt_id: "br-001",
            execution_intent_id: "ei-001",
            bind_outcome: "COMMITTED",
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            items: [
              {
                ...MOCK_ITEMS[0],
                bind_receipt_id: "br-001",
              },
            ],
            next_cursor: null,
            has_more: false,
          }),
      });

    const { result } = renderHook(() => useAuditData());

    await waitFor(() => {
      expect(result.current.bindReceiptIdFromQuery).toBe("br-001");
      expect(result.current.items).toHaveLength(1);
    });

    expect(mockFetch).toHaveBeenNthCalledWith(
      1,
      "/api/veritas/v1/governance/bind-receipts/br-001",
    );
    expect(mockFetch).toHaveBeenNthCalledWith(
      2,
      "/api/veritas/v1/trust/logs?limit=50",
      expect.any(Object),
    );
    expect(result.current.bindReceiptFoundInTimeline).toBe(true);
    expect(result.current.bindReceiptLookupDetail?.bindReceiptId).toBe("br-001");
    expect(result.current.showBindReceiptFallback).toBe(false);
    expect(result.current.filteredItems).toHaveLength(1);
    expect(result.current.selected?.bind_receipt_id).toBe("br-001");
    expect(result.current.detailTab).toBe("related");
  });

  it("preserves bind receipt detail and enables fallback when timeline miss occurs", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=br-777");
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            ok: true,
            bind_receipt: {
              bind_receipt_id: "br-777",
              execution_intent_id: "ei-777",
              final_outcome: "ESCALATED",
              escalation_reason: "manual-review",
              action_contract_id: "ac-777",
              authority_evidence_id: "ae-777",
              authority_evidence_hash: "hash-777",
              authority_validation_status: "stale",
              commit_boundary_result: "escalate",
              failed_predicates: [{ predicate_id: "p-1" }],
              stale_predicates: [{ predicate_id: "p-2" }],
              missing_predicates: [{ predicate_id: "p-3" }],
              refusal_basis: ["scope_denied"],
              escalation_basis: ["manual_review_required"],
              irreversibility_boundary_id: "ib-777",
              authority_check_result: { passed: true },
              constraint_check_result: { passed: false },
              drift_check_result: { result: "stable" },
              risk_check_result: { result: "block" },
            },
          }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () =>
          Promise.resolve({
            items: MOCK_ITEMS,
            next_cursor: null,
            has_more: false,
          }),
      });

    const { result } = renderHook(() => useAuditData());

    await waitFor(() => {
      expect(result.current.bindReceiptIdFromQuery).toBe("br-777");
      expect(result.current.bindReceiptLookupLoading).toBe(false);
      expect(result.current.bindReceiptFoundInTimeline).toBe(false);
      expect(result.current.showBindReceiptFallback).toBe(true);
    });

    expect(result.current.bindReceiptTimelineMiss).toBe(true);
    expect(result.current.bindReceiptLookupSucceeded).toBe(true);
    expect(result.current.bindReceiptLookupDetail).toMatchObject({
      bindReceiptId: "br-777",
      executionIntentId: "ei-777",
      finalOutcome: "ESCALATED",
      bindFailureReason: "manual-review",
      actionContractId: "ac-777",
      authorityEvidenceId: "ae-777",
      authorityEvidenceHash: "hash-777",
      authorityValidationStatus: "stale",
      commitBoundaryResult: "escalate",
      irreversibilityBoundaryId: "ib-777",
      refusalBasis: ["scope_denied"],
      escalationBasis: ["manual_review_required"],
    });
    expect(result.current.bindReceiptLookupDetail?.failedPredicates).toHaveLength(1);
    expect(result.current.bindReceiptLookupDetail?.stalePredicates).toHaveLength(1);
    expect(result.current.bindReceiptLookupDetail?.missingPredicates).toHaveLength(1);
  });

  it("includes bind receipt identifiers in cross-search all-field matching", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          items: [
            {
              ...MOCK_ITEMS[0],
              bind_receipt_id: "br-direct",
            },
            {
              ...MOCK_ITEMS[1],
              bind_receipt: { bind_receipt_id: "br-nested" },
            },
          ],
          next_cursor: null,
          has_more: false,
        }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    act(() => {
      result.current.setCrossSearch({ query: "br-direct", field: "all" });
    });
    expect(result.current.filteredItems).toHaveLength(1);
    expect(result.current.filteredItems[0].bind_receipt_id).toBe("br-direct");

    act(() => {
      result.current.setCrossSearch({ query: "br-nested", field: "all" });
    });
    expect(result.current.filteredItems).toHaveLength(1);
    expect(result.current.filteredItems[0].request_id).toBe("req-002");
  });

  it("handles invalid bind_receipt_id query param without fetch", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=bad%20value");

    const { result } = renderHook(() => useAuditData());

    await waitFor(() => {
      expect(result.current.bindReceiptLookupError).toContain("Invalid bind_receipt_id");
    });
    expect(result.current.bindReceiptLookupDetail).toBeNull();
    expect(result.current.showBindReceiptFallback).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("handles bind receipt not found", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=br-missing");
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 });

    const { result } = renderHook(() => useAuditData());

    await waitFor(() => {
      expect(result.current.bindReceiptLookupError).toContain("not found");
    });
    expect(result.current.bindReceiptLookupDetail).toBeNull();
    expect(result.current.showBindReceiptFallback).toBe(false);
  });

  it("handles bind receipt fetch failure", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=br-err");
    mockFetch.mockRejectedValueOnce(new Error("network"));

    const { result } = renderHook(() => useAuditData());

    await waitFor(() => {
      expect(result.current.bindReceiptLookupError).toContain("Network error");
    });
    expect(result.current.bindReceiptLookupDetail).toBeNull();
    expect(result.current.showBindReceiptFallback).toBe(false);
  });

  it("consumes decision_id query and focuses matched timeline item", async () => {
    window.history.replaceState({}, "", "/audit?decision_id=42");
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });

    await waitFor(() => {
      expect(result.current.decisionIdFromQuery).toBe("42");
      expect(result.current.selected?.decision_id).toBe("42");
      expect(result.current.queryTraceStatus).toBe("decision:matched");
    });
  });

  it("shows decision_id not found status when no timeline entry matches", async () => {
    window.history.replaceState({}, "", "/audit?decision_id=dec_missing");
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ items: MOCK_ITEMS, next_cursor: null, has_more: false }),
    });
    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });
    await waitFor(() => {
      expect(result.current.queryTraceStatus).toBe("decision:not-found");
    });
  });

  it("consumes execution_intent_id query and focuses matched timeline item", async () => {
    window.history.replaceState({}, "", "/audit?execution_intent_id=ei-123");
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          items: [{ ...MOCK_ITEMS[0], metadata: { execution_intent_id: "ei-123" } }],
          next_cursor: null,
          has_more: false,
        }),
    });

    const { result } = renderHook(() => useAuditData());
    await act(async () => {
      await result.current.loadLogs(null, true);
    });
    await waitFor(() => {
      expect(result.current.executionIntentIdFromQuery).toBe("ei-123");
      expect(result.current.queryTraceStatus).toBe("execution-intent:matched");
      expect(result.current.selected?.request_id).toBe("req-001");
    });
  });

});
