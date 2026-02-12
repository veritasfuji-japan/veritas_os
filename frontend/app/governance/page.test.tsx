import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import GovernanceControlPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GovernanceControlPage", () => {
  it("loads policy and previews diff before save", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        policy: {
          fuji_enabled: true,
          risk_threshold: 0.7,
          auto_stop_conditions: ["high_risk_detected"],
          log_retention_days: 90,
          audit_strength: "standard",
        },
      }),
    } as Response);

    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを取得" }));

    await waitFor(() => {
      expect(screen.getByLabelText("Risk threshold")).toHaveValue("0.7");
    });

    fireEvent.change(screen.getByLabelText("Risk threshold"), {
      target: { value: "0.85" },
    });

    expect(screen.getByText("risk_threshold")).toBeInTheDocument();
    expect(screen.getByText(/after: 0.85/)).toBeInTheDocument();
  });
});
