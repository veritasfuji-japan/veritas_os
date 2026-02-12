import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import GovernanceControlPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GovernanceControlPage", () => {
  it("loads and updates governance policy", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          fuji_enabled: true,
          risk_threshold: 0.55,
          auto_stop_conditions: ["fuji_rejected"],
          log_retention_days: 90,
          audit_intensity: "standard",
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          fuji_enabled: false,
          risk_threshold: 0.8,
          auto_stop_conditions: ["manual_override"],
          log_retention_days: 45,
          audit_intensity: "strict",
        }),
      } as Response);

    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), { target: { value: "test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "現在のpolicyを取得" }));

    await waitFor(() => {
      expect(screen.getByText(/差分プレビュー/)).not.toBeNull();
    });

    fireEvent.click(screen.getByLabelText("FUJIルール有効化"));
    fireEvent.change(screen.getByLabelText("リスク閾値 \(0.0-1.0\)"), { target: { value: "0.8" } });
    fireEvent.change(screen.getByLabelText("ログ保持期間（日）"), { target: { value: "45" } });
    fireEvent.change(screen.getByLabelText("監査強度"), { target: { value: "strict" } });
    fireEvent.change(screen.getByLabelText("自動停止条件（1行1条件）"), {
      target: { value: "manual_override" },
    });

    fireEvent.click(screen.getByRole("button", { name: "policyを更新" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(2);
    });
  });
});
