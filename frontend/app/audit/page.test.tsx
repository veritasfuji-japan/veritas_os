import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TrustLogExplorerPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
  window.history.replaceState({}, "", "/audit");
});

const MOCK_ITEMS_CHAINED = [
  {
    request_id: "req-100",
    stage: "value_core",
    severity: "low",
    status: "allow",
    created_at: "2026-02-12T00:00:00Z",
    sha256: "cccccccccccccccccccccccccccccccc",
    sha256_prev: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    decision_id: "dec-100",
    policy_version: "v1.2",
    sources: ["memory"],
    critics: [],
    checks: ["fuji"],
    approver: "system",
  },
  {
    request_id: "req-099",
    stage: "planner",
    severity: "medium",
    status: "allow",
    created_at: "2026-02-11T00:00:00Z",
    sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    sha256_prev: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    decision_id: "dec-099",
    replay_id: "rpl-001",
    policy_version: "v1.1",
    sources: ["web"],
    critics: [],
    checks: ["fuji"],
    approver: "system",
  },
];

function mockFetchWithItems(items: unknown[] = MOCK_ITEMS_CHAINED) {
  return vi.spyOn(global, "fetch").mockResolvedValueOnce({
    ok: true,
    json: async () => ({
      items,
      cursor: "0",
      next_cursor: items.length >= 50 ? "2" : null,
      limit: 50,
      has_more: items.length >= 50,
    }),
  } as Response);
}

async function loadLogs() {
  fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));
  await waitFor(() => {
    expect(screen.getByText(/表示件数: /)).toBeInTheDocument();
  });
}

describe("TrustLogExplorerPage", () => {
  it("renders decision trace card and matched status from decision_id query", async () => {
    window.history.replaceState({}, "", "/audit?decision_id=dec-100");
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();
    expect(screen.getByText("Decision Artifact Trace")).toBeInTheDocument();
    expect(screen.getAllByText("decision_id:").length).toBeGreaterThan(0);
    expect(screen.getAllByText("dec-100").length).toBeGreaterThan(0);
    expect(screen.getByText(/Matched decision artifact in timeline|関連する decision artifact をタイムラインで選択しました/)).toBeInTheDocument();
  });

  it("renders execution intent trace not-found status", async () => {
    window.history.replaceState({}, "", "/audit?execution_intent_id=ei-missing");
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();
    expect(screen.getByText("Execution Intent Trace")).toBeInTheDocument();
    expect(screen.getAllByText("ei-missing").length).toBeGreaterThan(0);
    expect(screen.getByText(/Execution intent was not found in the currently loaded timeline|execution intent は現在読み込まれているタイムラインに見つかりません/)).toBeInTheDocument();
  });

  it("loads paged trust logs and renders timeline items", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          { request_id: "req-1", stage: "value", created_at: "2026-02-12T00:00:00Z", sources: [], critics: [], checks: [], approver: "system" },
          { request_id: "req-2", stage: "fuji", created_at: "2026-02-11T00:00:00Z", sources: [], critics: [], checks: [], approver: "system" },
        ],
        cursor: "0",
        next_cursor: "2",
        limit: 50,
        has_more: true,
      }),
    } as Response);

    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getAllByText("value").length).toBeGreaterThanOrEqual(2);
      expect(screen.getAllByText("fuji").length).toBeGreaterThanOrEqual(2);
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/表示件数: 2/)).toBeInTheDocument();
  });

  it("shows validation error when trust logs response shape is invalid", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [{ request_id: 10 }],
        cursor: "0",
        next_cursor: null,
        limit: 50,
        has_more: false,
      }),
    } as Response);

    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText("レスポンス形式エラー: trust logs の形式が不正です。")).toBeInTheDocument();
    });
  });

  it("shows timeout error when trust logs request is aborted", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));

    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText("タイムアウト: trust logs 取得が時間内に完了しませんでした。")).toBeInTheDocument();
    });
  });

  it("silently drops aborted request_id search", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));

    render(<TrustLogExplorerPage />);
    fireEvent.change(screen.getByLabelText("リクエストIDで検索"), {
      target: { value: "req-timeout" },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    // AbortError is now silently dropped — no error message should appear
    await waitFor(() => {
      expect(screen.queryByText("タイムアウト: request_id 検索が時間内に完了しませんでした。")).not.toBeInTheDocument();
    });
  });

  it("verifies hash chain and shows tamper-proof stamp", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    const decisionSelect = screen.getByLabelText("検証対象の意思決定ID");
    fireEvent.change(decisionSelect, { target: { value: "dec-100" } });
    fireEvent.click(screen.getByRole("button", { name: "ハッシュチェーン検証" }));

    await waitFor(() => {
      expect(screen.getByText("TAMPER-PROOF ✅")).toBeInTheDocument();
    }, { timeout: 4000 });
  });

  it("shows period validation error when generating report without dates", async () => {
    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "JSON生成" }));

    await waitFor(() => {
      expect(screen.getByText("PII/metadata warning を確認してください。")).toBeInTheDocument();
    });
  });

  it("builds regulatory report summary from selected period", async () => {
    mockFetchWithItems();

    const createObjectUrlMock = vi.fn(() => "blob:report");
    const revokeObjectUrlMock = vi.fn();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = createObjectUrlMock;
    URL.revokeObjectURL = revokeObjectUrlMock;
    const clickMock = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<TrustLogExplorerPage />);
    await loadLogs();

    const dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-02-10" } });
    fireEvent.change(dateInputs[1], { target: { value: "2026-02-12" } });

    // Check the PII acknowledgement checkbox
    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(screen.getByRole("button", { name: "JSON生成" }));

    await waitFor(() => {
      expect(screen.getByText(/entries: 2/)).toBeInTheDocument();
    });

    expect(createObjectUrlMock).toHaveBeenCalledTimes(1);
    expect(clickMock).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrlMock).toHaveBeenCalledTimes(1);

    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    clickMock.mockRestore();
  });

  it("generates printable report without using HTML string injection", async () => {
    mockFetchWithItems();

    const printDocument = document.implementation.createHTMLDocument("report");
    const printMock = vi.fn();
    const focusMock = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({
      document: printDocument,
      focus: focusMock,
      print: printMock,
    } as unknown as Window);

    render(<TrustLogExplorerPage />);
    await loadLogs();

    const dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-02-10" } });
    fireEvent.change(dateInputs[1], { target: { value: "2026-02-12" } });

    // Select PDF format and acknowledge PII
    const pdfRadio = screen.getByDisplayValue("pdf");
    fireEvent.click(pdfRadio);

    const checkboxes = screen.getAllByRole("checkbox");
    fireEvent.click(checkboxes[0]);
    fireEvent.click(screen.getByRole("button", { name: "PDF生成" }));

    await waitFor(() => {
      expect(printMock).toHaveBeenCalledTimes(1);
    });
    expect(focusMock).toHaveBeenCalledTimes(1);
    expect(printDocument.body.textContent).toContain("Regulatory Report Generator");
  });

  it("exposes accessible labels for verification and export controls", () => {
    render(<TrustLogExplorerPage />);

    expect(screen.getByLabelText("検証対象の意思決定ID")).toBeInTheDocument();
    expect(screen.getByLabelText("監査レポート開始日")).toBeInTheDocument();
    expect(screen.getByLabelText("監査レポート終了日")).toBeInTheDocument();
  });

  /* ================================================================ */
  /*  New tests for enhanced audit interface                           */
  /* ================================================================ */

  it("renders enhanced audit summary with verified/broken/missing/orphan counts", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    // Should show summary grid
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Broken")).toBeInTheDocument();
    expect(screen.getByText("Missing")).toBeInTheDocument();
    expect(screen.getByText("Orphan")).toBeInTheDocument();
    expect(screen.getByText("リプレイ連携")).toBeInTheDocument();
    // Chain integrity percentage
    expect(screen.getByText(/チェーン整合率/)).toBeInTheDocument();
  });

  it("shows policy version distribution when data includes policy_version", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    expect(screen.getByText("ポリシーバージョン分布")).toBeInTheDocument();
    expect(screen.getByText(/v1\.2: 1/)).toBeInTheDocument();
    expect(screen.getByText(/v1\.1: 1/)).toBeInTheDocument();
  });

  it("shows cross-search field selector and filters by decision_id", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    const fieldSelect = screen.getByLabelText("検索フィールド");
    expect(fieldSelect).toBeInTheDocument();

    // Switch to decision_id field and search
    fireEvent.change(fieldSelect, { target: { value: "decision_id" } });
    const searchInput = screen.getByLabelText("cross-search");
    fireEvent.change(searchInput, { target: { value: "dec-100" } });

    await waitFor(() => {
      expect(screen.getByText(/一致: 1/)).toBeInTheDocument();
    });
  });

  it("renders detail tabs and switches between them", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    // Summary tab should be visible by default
    expect(screen.getByText("サマリー")).toBeInTheDocument();
    expect(screen.getByText("メタデータ")).toBeInTheDocument();
    expect(screen.getByText("ハッシュ")).toBeInTheDocument();
    expect(screen.getByText("関連ID")).toBeInTheDocument();
    expect(screen.getByText("Raw JSON")).toBeInTheDocument();

    // Click Hash tab
    fireEvent.click(screen.getByText("ハッシュ"));
    await waitFor(() => {
      expect(screen.getByText("現在")).toBeInTheDocument();
    });
  });

  it("shows export target count preview when dates are selected", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    const dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-02-10" } });
    fireEvent.change(dateInputs[1], { target: { value: "2026-02-12" } });

    await waitFor(() => {
      expect(screen.getByText(/エクスポート対象: 2/)).toBeInTheDocument();
    });
  });

  it("shows redaction mode options in export section", () => {
    render(<TrustLogExplorerPage />);

    expect(screen.getByText("墨消しモード")).toBeInTheDocument();
    expect(screen.getByText("出力形式")).toBeInTheDocument();
    expect(screen.getByDisplayValue("full")).toBeInTheDocument();
    expect(screen.getByDisplayValue("redacted")).toBeInTheDocument();
    expect(screen.getByDisplayValue("metadata-only")).toBeInTheDocument();
  });

  it("displays empty state guidance when no logs are loaded", () => {
    render(<TrustLogExplorerPage />);

    expect(screen.getByRole("button", { name: "最新ログを読み込み" })).toBeInTheDocument();
    // Empty state guidance
    expect(screen.getByText(/まず「最新ログを読み込み」で監査ログを取得してください/)).toBeInTheDocument();
    // Audit summary empty state
    expect(screen.getByText(/ログを読み込むと、ここに全体の監査サマリーが表示されます/)).toBeInTheDocument();
  });

  it("renders timeline column headers when items are loaded", async () => {
    mockFetchWithItems();
    render(<TrustLogExplorerPage />);
    await loadLogs();

    expect(screen.getByText("重要度")).toBeInTheDocument();
    expect(screen.getByText("タイムスタンプ")).toBeInTheDocument();
    expect(screen.getByText("チェーン")).toBeInTheDocument();
  });

  it("consumes governance bind receipt query URL and shows trace focus status", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=br-001");
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ bind_receipt_id: "br-001" }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          items: [
            {
              ...MOCK_ITEMS_CHAINED[0],
              bind_receipt_id: "br-001",
            },
          ],
          cursor: "0",
          next_cursor: null,
          limit: 50,
          has_more: false,
        }),
      } as Response);

    render(<TrustLogExplorerPage />);

    await waitFor(() => {
      expect(screen.getByText("Bind Receipt Trace")).toBeInTheDocument();
      expect(screen.getByText("br-001")).toBeInTheDocument();
      expect(screen.getByText("関連する監査ログをタイムラインで選択しました。")).toBeInTheDocument();
    });
    expect(screen.queryByText("Bind check summary")).not.toBeInTheDocument();
  });

  it("renders compact bind receipt fallback detail when timeline misses the receipt", async () => {
    window.history.replaceState({}, "", "/audit?bind_receipt_id=br-001");
    vi.spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          bind_receipt_id: "br-001",
          execution_intent_id: "exec-001",
          final_outcome: "BLOCKED",
          bind_failure_reason: "policy_denied",
          action_contract_id: "ac-1",
          authority_evidence_id: "ae-1",
          authority_evidence_hash: "hash-1",
          authority_validation_status: "valid",
          commit_boundary_result: "block",
          failed_predicates: [{ predicate_id: "p1" }],
          stale_predicates: [{ predicate_id: "p2" }],
          missing_predicates: [{ predicate_id: "p3" }],
          refusal_basis: ["authority_missing"],
          escalation_basis: ["manual_review_required"],
          irreversibility_boundary_id: "ib-1",
          authority_check_result: { passed: true },
          constraint_check_result: { passed: false },
          drift_check_result: { result: "warn" },
          risk_check_result: null,
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          items: MOCK_ITEMS_CHAINED,
          cursor: "0",
          next_cursor: null,
          limit: 50,
          has_more: false,
        }),
      } as Response);

    render(<TrustLogExplorerPage />);

    await waitFor(() => {
      expect(screen.getByText("Bind Receipt Trace")).toBeInTheDocument();
      expect(screen.getByText("Runtime Authority")).toBeInTheDocument();
      expect(screen.getByText("bindFailureReason")).toBeInTheDocument();
      expect(screen.getByText("policy_denied")).toBeInTheDocument();
      expect(screen.getByText("execution_intent_id")).toBeInTheDocument();
      expect(screen.getByText("exec-001")).toBeInTheDocument();
      expect(screen.getByText("BLOCKED")).toBeInTheDocument();
      expect(screen.getByText("Regulated action governance")).toBeInTheDocument();
      expect(screen.getByText("Action Contract")).toBeInTheDocument();
      expect(screen.getByText("Authority Evidence")).toBeInTheDocument();
      expect(screen.getByText("Commit Boundary")).toBeInTheDocument();
      expect(screen.getByText("Failed Predicates")).toBeInTheDocument();
      expect(screen.getByText("Refusal Basis")).toBeInTheDocument();
      expect(screen.getByText("Escalation Basis")).toBeInTheDocument();
      expect(screen.getByText("Irreversibility Boundary")).toBeInTheDocument();
      expect(screen.getByText("authorityCheckResult")).toBeInTheDocument();
      expect(screen.getByText("PASS")).toBeInTheDocument();
      expect(screen.getByText("FAIL")).toBeInTheDocument();
      expect(screen.getByText("WARN")).toBeInTheDocument();
      expect(screen.getByText("Raw fallback detail")).toBeInTheDocument();
      expect(
        screen.getByText("bind receipt は取得済みですが、現在読み込まれているタイムラインには未表示です。"),
      ).toBeInTheDocument();
    });
  });

});
