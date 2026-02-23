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

    // Set API key first (button is disabled without it)
    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });

    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      // Stage names appear both in the timeline entries and the stage filter dropdown.
      // Use getAllByText to handle the duplicate matches.
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

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });

    fireEvent.click(screen.getByRole("button", { name: "最新ログを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText("レスポンス形式エラー: trust logs の形式が不正です。")).toBeInTheDocument();
    });
  });

});
