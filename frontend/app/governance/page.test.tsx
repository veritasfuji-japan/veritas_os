import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import GovernanceControlPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

const MOCK_POLICY = {
  ok: true,
  policy: {
    version: "governance_v1",
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
      allow_upper: 0.4,
      warn_upper: 0.65,
      human_review_upper: 0.85,
      deny_upper: 1.0,
    },
    auto_stop: {
      enabled: true,
      max_risk_score: 0.85,
      max_consecutive_rejects: 5,
      max_requests_per_minute: 60,
    },
    log_retention: {
      retention_days: 90,
      audit_level: "full",
      include_fields: ["status", "risk"],
      redact_before_log: true,
      max_log_size: 10000,
    },
    rollout_controls: {
      strategy: "disabled",
      canary_percent: 0,
      stage: 0,
      staged_enforcement: false,
    },
    approval_workflow: {
      human_review_ticket: "",
      human_review_required: false,
      approver_identity_binding: true,
      approver_identities: [],
    },
    wat: {
      enabled: true,
      issuance_mode: "shadow_only",
      require_observable_digest: true,
      default_ttl_seconds: 300,
    },
    psid: {
      display_length: 12,
    },
    shadow_validation: {
      replay_binding_required: true,
      partial_validation_default: "non_admissible",
      warning_only_until: "2026-12-31T00:00:00Z",
      timestamp_skew_tolerance_seconds: 30,
    },
    revocation: {
      mode: "bounded_eventual_consistency",
    },
    drift_scoring: {
      policy_weight: 0.4,
      signature_weight: 0.3,
      observable_weight: 0.2,
      temporal_weight: 0.1,
      healthy_threshold: 0.2,
      critical_threshold: 0.5,
    },
    updated_at: "2026-02-12T00:00:00+00:00",
    updated_by: "system",
  },
};

beforeEach(() => {
  let seq = 0;
  vi.stubGlobal("crypto", { randomUUID: vi.fn(() => `uuid-${seq++}`) });
  vi.stubGlobal("confirm", vi.fn(() => true));
});

function mockPolicyFetch(): ReturnType<typeof vi.spyOn> {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => MOCK_POLICY,
  } as Response);
}

describe("GovernanceControlPage", () => {
  it("renders governance header and load button", () => {
    render(<GovernanceControlPage />);
    expect(screen.getByRole("heading", { name: "Governance Control" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ポリシーを読み込む" })).toBeInTheDocument();
  });

  it("shows empty state before policy load", () => {
    render(<GovernanceControlPage />);
    expect(screen.getByText("ポリシー未読み込み")).toBeInTheDocument();
  });

  it("shows role capabilities", () => {
    render(<GovernanceControlPage />);
    expect(screen.getByText("Admin（管理者）")).toBeInTheDocument();
    expect(screen.getByText("全操作権限")).toBeInTheDocument();
  });

  it("shows mode explanation details", () => {
    render(<GovernanceControlPage />);
    expect(screen.getByText("通常運用モード")).toBeInTheDocument();
  });

  it("loads policy and shows control-plane sections", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText("Policy Meta")).toBeInTheDocument();
      expect(screen.getByText("FUJI rules / thresholds / escalation")).toBeInTheDocument();
      expect(screen.getByText("WAT Settings")).toBeInTheDocument();
      expect(screen.getByText("Current vs Draft Diff")).toBeInTheDocument();
      expect(screen.getByText("Apply Flow")).toBeInTheDocument();
      expect(screen.getByText("Policy Bundle Promotion")).toBeInTheDocument();
      expect(screen.getByText("Change History")).toBeInTheDocument();
    });
  });



  it("renders backend-aligned WAT controls", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText("wat.enabled")).toBeInTheDocument();
      expect(screen.getByLabelText("wat.issuance_mode")).toBeInTheDocument();
      expect(screen.getByText("psid.display_length")).toBeInTheDocument();
      expect(screen.getByText("shadow_validation.replay_binding_required")).toBeInTheDocument();
      expect(screen.getByLabelText("revocation.mode")).toBeInTheDocument();
      expect(screen.queryByText("wat_settings")).not.toBeInTheDocument();
    });
  });

  it("shows policy state model fields including approval status", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText("Current Version")).toBeInTheDocument();
      expect(screen.getByText("Draft Version")).toBeInTheDocument();
      expect(screen.getByText("Approval Status")).toBeInTheDocument();
      expect(screen.getByText("effective_at")).toBeInTheDocument();
      expect(screen.getByText("last_applied")).toBeInTheDocument();
      expect(screen.getByText("updated_by")).toBeInTheDocument();
    });
  });

  it("supports draft edits and displays categorized diff entries", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "PII Check" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("switch", { name: "PII Check" }));
    expect(screen.getByText("fuji_rules.pii_check")).toBeInTheDocument();
    expect(screen.getByText("ルール変更")).toBeInTheDocument();
  });

  it("shows approval workflow when changes exist", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "PII Check" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("switch", { name: "PII Check" }));
    expect(screen.getByText("Approval Workflow")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /approve|承認/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reject|拒否/ })).toBeInTheDocument();
  });

  it("shows Risk Impact Analysis after load", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText("Risk Impact Analysis")).toBeInTheDocument();
      expect(screen.getByText("Current Policy")).toBeInTheDocument();
      expect(screen.getByText("Pending Impact")).toBeInTheDocument();
      expect(screen.getByText(/from baseline/)).toBeInTheDocument();
    });
  });

  it("applies RBAC gating in UI", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "適用" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("role"), { target: { value: "viewer" } });
    expect(screen.getByRole("button", { name: "適用" })).toBeDisabled();
    expect(screen.getByText("RBAC: apply/rollback は admin のみ実行可能です。")).toBeInTheDocument();
  });

  it("disables toggle switches for viewer role", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "PII Check" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("role"), { target: { value: "viewer" } });
    expect(screen.getByRole("switch", { name: "PII Check" })).toBeDisabled();
    expect(screen.getByLabelText("wat.issuance_mode")).toBeDisabled();
    expect(screen.getByText("Read-only role: WAT settings are visible but cannot be mutated.")).toBeInTheDocument();
  });

  it("executes dry-run and shows status", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "ドライラン" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("switch", { name: "PII Check" }));
    fireEvent.click(screen.getByRole("button", { name: "ドライラン" }));

    // applyPolicy が ConfirmDialog を表示するのでダイアログ内「確認する」をクリック
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "確認する" })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole("button", { name: "確認する" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Dry-run を完了しました。適用はされていません。");
    });
  });

  it("shows validation error for malformed policy responses", async () => {
    vi.spyOn(global, "fetch")
      // First call: EUAIActGovernanceDashboard compliance/config on mount
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ config: { eu_ai_act_mode: false, safety_threshold: 0.8 } }),
      } as Response)
      // Second call: managed SSE probe (/api/veritas/v1/events)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({}),
      } as Response)
      // Third call: governance/policy triggered by button click
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, policy: { updated_by: 123 } }),
      } as Response);

    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("レスポンスの検証に失敗しました");
    });
  });

  it("shows TrustLog with policy severity tag after load", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText(/policy version governance_v1 loaded/)).toBeInTheDocument();
    });
  });
});
