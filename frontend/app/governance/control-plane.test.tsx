import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import GovernanceControlPage from "./page";

const policyResponse = {
  ok: true,
  policy: {
    version: "v1.2.3",
    fuji_rules: {
      pii_check: true,
      self_harm_block: true,
      illicit_block: true,
      violence_review: true,
      minors_review: true,
      keyword_hard_block: true,
      keyword_soft_flag: true,
      llm_safety_head: true,
    },
    risk_thresholds: {
      allow_upper: 0.2,
      warn_upper: 0.4,
      human_review_upper: 0.6,
      deny_upper: 0.8,
    },
    auto_stop: {
      enabled: true,
      max_risk_score: 0.9,
      max_consecutive_rejects: 3,
      max_requests_per_minute: 120,
    },
    log_retention: {
      retention_days: 30,
      audit_level: "standard",
      include_fields: ["risk"],
      redact_before_log: true,
      max_log_size: 1000,
    },
    rollout_controls: {
      strategy: "canary",
      canary_percent: 10,
      stage: 1,
      staged_enforcement: true,
    },
    approval_workflow: {
      human_review_ticket: "GOV-999",
      human_review_required: true,
      approver_identity_binding: true,
      approver_identities: ["admin-a", "admin-b"],
    },
    updated_at: "2026-01-01T00:00:00+00:00",
    updated_by: "admin",
  },
};

describe("Governance control plane", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => policyResponse }));
    let seq = 0;
    vi.stubGlobal("crypto", { randomUUID: () => `uuid-${seq++}` });
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  });

  it("renders policy metadata after loading", async () => {
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText("Current Version")).toBeInTheDocument();
      expect(screen.getByText("Draft Version")).toBeInTheDocument();
      expect(screen.getByText("effective_at")).toBeInTheDocument();
      expect(screen.getByText("last_applied")).toBeInTheDocument();
      expect(screen.getByText("updated_by")).toBeInTheDocument();
      expect(screen.getByText("Approval Status")).toBeInTheDocument();
    });
  });

  it("gates apply button for viewer role", async () => {
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "適用" })).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("role"), { target: { value: "viewer" } });
    expect(screen.getByRole("button", { name: "適用" })).toBeDisabled();
  });
});
