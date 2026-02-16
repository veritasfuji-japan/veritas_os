import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import GovernanceControlPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GovernanceControlPage", () => {
  it("loads policy and updates via API", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          fuji_enabled: true,
          risk_threshold: 0.6,
          auto_stop_conditions: ["policy_violation_detected"],
          log_retention_days: 90,
          audit_intensity: "standard",
          updated_at: "2026-02-16T00:00:00Z",
          version: 1,
        }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          fuji_enabled: false,
          risk_threshold: 0.4,
          auto_stop_conditions: ["manual_override"],
          log_retention_days: 120,
          audit_intensity: "high",
          updated_at: "2026-02-16T00:01:00Z",
          version: 2,
        }),
      } as Response);

    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), { target: { value: "test-key" } });
    fireEvent.click(screen.getByRole("button", { name: "現在のpolicyを読み込み" }));

    await waitFor(() => {
      expect(screen.getByText("policy を読み込みました。")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.change(screen.getByDisplayValue("0.60"), { target: { value: "0.40" } });
    fireEvent.change(screen.getByDisplayValue("policy_violation_detected"), {
      target: { value: "manual_override" },
    });
    fireEvent.change(screen.getByDisplayValue("90"), { target: { value: "120" } });
    fireEvent.change(screen.getByDisplayValue("standard"), { target: { value: "high" } });

    fireEvent.click(screen.getByRole("button", { name: "policy更新" }));

    await waitFor(() => {
      expect(screen.getByText("policy を更新しました。")).toBeInTheDocument();
      expect(screen.getByText(/risk_threshold: 0.6 -> 0.4/)).toBeInTheDocument();
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
