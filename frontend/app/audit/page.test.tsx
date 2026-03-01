import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TrustLogExplorerPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TrustLogExplorerPage", () => {
  it("loads paged trust logs and renders timeline items", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          items: [
            { request_id: "req-1", stage: "value", created_at: "2026-02-12T00:00:00Z" },
            { request_id: "req-2", stage: "fuji", created_at: "2026-02-11T00:00:00Z" },
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

  it("shows timeout error when request_id search is aborted", async () => {
    vi.spyOn(global, "fetch").mockRejectedValueOnce(new DOMException("Aborted", "AbortError"));

    render(<TrustLogExplorerPage />);

    fireEvent.change(screen.getByLabelText("request_id"), {
      target: { value: "req-timeout" },
    });
    fireEvent.click(screen.getByRole("button", { name: "検索" }));

    await waitFor(() => {
      expect(screen.getByText("タイムアウト: request_id 検索が時間内に完了しませんでした。")).toBeInTheDocument();
    });
  });

  it("verifies hash chain and shows tamper-proof stamp", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            request_id: "req-100",
            stage: "value_core",
            created_at: "2026-02-12T00:00:00Z",
            sha256: "cccccccccccccccccccccccccccccccc",
            sha256_prev: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          },
          {
            request_id: "req-099",
            stage: "planner",
            created_at: "2026-02-11T00:00:00Z",
            sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            sha256_prev: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          },
        ],
        cursor: "0",
        next_cursor: null,
        limit: 50,
        has_more: false,
      }),
    } as Response);

    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText(/表示件数: 2/)).toBeInTheDocument();
    });

    const comboBoxes = screen.getAllByRole("combobox");
    fireEvent.change(comboBoxes[1], {
      target: { value: "req-100" },
    });
    fireEvent.click(screen.getByRole("button", { name: "ハッシュチェーン検証" }));

    await waitFor(() => {
      expect(screen.getByText("TAMPER-PROOF ✅")).toBeInTheDocument();
    }, { timeout: 4000 });
  });

  it("shows period validation error when generating report without dates", async () => {
    render(<TrustLogExplorerPage />);

    fireEvent.click(screen.getByRole("button", { name: "JSON生成" }));

    await waitFor(() => {
      expect(screen.getByText("期間を指定してください。")).toBeInTheDocument();
    });
  });

  it("builds regulatory report summary from selected period", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            request_id: "req-100",
            stage: "fuji",
            status: "rejected",
            created_at: "2026-02-12T10:00:00Z",
            sha256: "cccccccccccccccccccccccccccccccc",
            sha256_prev: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          },
          {
            request_id: "req-099",
            stage: "fuji",
            status: "allow",
            created_at: "2026-02-11T10:00:00Z",
            sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            sha256_prev: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          },
        ],
        cursor: "0",
        next_cursor: null,
        limit: 50,
        has_more: false,
      }),
    } as Response);

    const createObjectUrlMock = vi.fn(() => "blob:report");
    const revokeObjectUrlMock = vi.fn();
    const originalCreateObjectURL = URL.createObjectURL;
    const originalRevokeObjectURL = URL.revokeObjectURL;
    URL.createObjectURL = createObjectUrlMock;
    URL.revokeObjectURL = revokeObjectUrlMock;
    const clickMock = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText(/表示件数: 2/)).toBeInTheDocument();
    });

    const dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-02-10" } });
    fireEvent.change(dateInputs[1], { target: { value: "2026-02-12" } });

    fireEvent.click(screen.getByRole("button", { name: "JSON生成" }));

    await waitFor(() => {
      expect(screen.getByText("entries: 2 / decision_ids: 2")).toBeInTheDocument();
      expect(screen.getByText("FUJI rejection: 1/2 (50.0%)")).toBeInTheDocument();
    });

    expect(createObjectUrlMock).toHaveBeenCalledTimes(1);
    expect(clickMock).toHaveBeenCalledTimes(1);
    expect(revokeObjectUrlMock).toHaveBeenCalledTimes(1);

    URL.createObjectURL = originalCreateObjectURL;
    URL.revokeObjectURL = originalRevokeObjectURL;
    clickMock.mockRestore();
  });


  it("generates printable report without using HTML string injection", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        items: [
          {
            request_id: "req-safe-1",
            stage: "fuji",
            status: "allow",
            created_at: "2026-02-12T10:00:00Z",
            sha256: "cccccccccccccccccccccccccccccccc",
            sha256_prev: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
          },
          {
            request_id: "req-safe-2",
            stage: "planner",
            status: "approved",
            created_at: "2026-02-11T10:00:00Z",
            sha256: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            sha256_prev: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          },
        ],
        cursor: "0",
        next_cursor: null,
        limit: 50,
        has_more: false,
      }),
    } as Response);

    const printDocument = document.implementation.createHTMLDocument("report");
    const printMock = vi.fn();
    const focusMock = vi.fn();
    vi.spyOn(window, "open").mockReturnValue({
      document: printDocument,
      focus: focusMock,
      print: printMock,
    } as unknown as Window);

    render(<TrustLogExplorerPage />);
    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText(/表示件数: 2/)).toBeInTheDocument();
    });

    const dateInputs = document.querySelectorAll('input[type="date"]');
    fireEvent.change(dateInputs[0], { target: { value: "2026-02-10" } });
    fireEvent.change(dateInputs[1], { target: { value: "2026-02-12" } });

    fireEvent.click(screen.getByRole("button", { name: "PDF生成" }));

    await waitFor(() => {
      expect(printMock).toHaveBeenCalledTimes(1);
    });
    expect(focusMock).toHaveBeenCalledTimes(1);
    expect(printDocument.body.textContent).toContain("Regulatory Report Generator");
  });

});
