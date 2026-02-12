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
      expect(screen.getByText("value")).not.toBeNull();
      expect(screen.getByText("fuji")).not.toBeNull();
    });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/表示件数: 2/)).not.toBeNull();
  });
});
