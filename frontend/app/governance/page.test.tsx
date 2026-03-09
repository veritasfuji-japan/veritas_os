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

  it("loads policy and shows control-plane sections", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText("Policy Meta")).toBeInTheDocument();
      expect(screen.getByText("FUJI rules / thresholds / escalation")).toBeInTheDocument();
      expect(screen.getByText("Current vs Draft Diff")).toBeInTheDocument();
      expect(screen.getByText("Apply Flow")).toBeInTheDocument();
      expect(screen.getByText("Change History")).toBeInTheDocument();
    });
  });

  it("shows policy state model fields", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByText(/^policy version:/i)).toBeInTheDocument();
      expect(screen.getByText(/effective_at:/i)).toBeInTheDocument();
      expect(screen.getByText(/last_applied:/i)).toBeInTheDocument();
      expect(screen.getByText(/updated_by:/i)).toBeInTheDocument();
    });
  });

  it("supports draft edits and displays diff entries", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);

    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("switch", { name: "PII Check" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("switch", { name: "PII Check" }));
    expect(screen.getByText("fuji_rules.pii_check")).toBeInTheDocument();
  });

  it("applies RBAC gating in UI", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "apply" })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText("role"), { target: { value: "viewer" } });
    expect(screen.getByRole("button", { name: "apply" })).toBeDisabled();
    expect(screen.getByText("RBAC: apply/rollback は admin のみ実行可能です。")).toBeInTheDocument();
  });

  it("executes dry-run and shows status", async () => {
    mockPolicyFetch();
    render(<GovernanceControlPage />);
    fireEvent.click(screen.getByRole("button", { name: "ポリシーを読み込む" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "dry-run" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("switch", { name: "PII Check" }));
    fireEvent.click(screen.getByRole("button", { name: "dry-run" }));

    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Dry-run を完了しました。適用はされていません。");
    });
  });

  it("shows validation error for malformed policy responses", async () => {
    vi.spyOn(global, "fetch").mockResolvedValueOnce({
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
});
