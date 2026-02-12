import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import GovernanceControlPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

describe("GovernanceControlPage", () => {
  it("loads policy and updates diff preview", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          policy: {
            fuji_enabled: true,
            risk_threshold: 0.55,
            auto_stop_conditions: ["critical_fuji_violation"],
            log_retention_days: 120,
            audit_intensity: "standard",
          },
        }),
      } as Response);

    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });

    fireEvent.click(screen.getByRole("button", { name: "現在ポリシー取得" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(screen.getByText(/"risk_threshold": 0.55/)).toBeInTheDocument();
    });
  });

  it("submits updated policy payload", async () => {
    const fetchMock = vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        before: {
          fuji_enabled: true,
          risk_threshold: 0.65,
          auto_stop_conditions: ["critical_fuji_violation", "trust_chain_break"],
          log_retention_days: 180,
          audit_intensity: "standard",
        },
        policy: {
          fuji_enabled: false,
          risk_threshold: 0.4,
          auto_stop_conditions: ["critical_fuji_violation"],
          log_retention_days: 90,
          audit_intensity: "strict",
        },
      }),
    } as Response);

    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.change(screen.getByLabelText("FUJI rule switch"), {
      target: { value: "disabled" },
    });
    fireEvent.change(screen.getByLabelText("Log retention days"), {
      target: { value: "90" },
    });

    fireEvent.click(screen.getByRole("button", { name: "ポリシー更新" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    });

    const call = fetchMock.mock.calls[0];
    expect(call[0]).toContain("/v1/governance/policy");
    expect(String((call[1] as RequestInit)?.body)).toContain('"fuji_enabled":false');
  });
});
