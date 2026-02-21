import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import GovernanceControlPage from "./page";

afterEach(() => {
  vi.restoreAllMocks();
});

const MOCK_POLICY = {
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
    include_fields: ["status", "risk", "reasons", "violations", "categories"],
    redact_before_log: true,
    max_log_size: 10000,
  },
  updated_at: "2026-02-12T00:00:00Z",
  updated_by: "system",
};

function mockFetchPolicy(): ReturnType<typeof vi.spyOn> {
  return vi.spyOn(global, "fetch").mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ ok: true, policy: MOCK_POLICY }),
  } as Response);
}

describe("GovernanceControlPage", () => {
  it("renders header and connection card", () => {
    render(<GovernanceControlPage />);
    expect(screen.getByText("Governance Control")).toBeInTheDocument();
    expect(screen.getByText("ポリシーを読み込む")).toBeInTheDocument();
  });

  it("loads and displays policy sections after fetch", async () => {
    mockFetchPolicy();
    render(<GovernanceControlPage />);

    // Enter API key and click load
    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("FUJI Rules")).toBeInTheDocument();
      expect(screen.getByText("Risk Thresholds (リスク閾値)")).toBeInTheDocument();
      expect(screen.getByText("Auto-Stop Conditions (自動停止条件)")).toBeInTheDocument();
      expect(screen.getByText("Log Retention / Audit (ログ保持・監査)")).toBeInTheDocument();
      expect(screen.getByText("Diff Preview (変更差分)")).toBeInTheDocument();
    });
  });

  it("shows FUJI rule toggles", async () => {
    mockFetchPolicy();
    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("PII Check (個人情報検査)")).toBeInTheDocument();
      expect(screen.getByText("LLM Safety Head (AI安全ヘッド)")).toBeInTheDocument();
    });
  });

  it("shows diff preview when a toggle is changed", async () => {
    mockFetchPolicy();
    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("PII Check (個人情報検査)")).toBeInTheDocument();
    });

    // Toggle PII check off
    const piiToggle = screen.getByRole("switch", { name: "PII Check (個人情報検査)" });
    fireEvent.click(piiToggle);

    // Should show unsaved warning
    expect(screen.getByText("未保存の変更があります")).toBeInTheDocument();
  });

  it("shows no-change message when policy is unchanged", async () => {
    mockFetchPolicy();
    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("変更はありません。")).toBeInTheDocument();
    });
  });

  it("sends PUT on save and shows success", async () => {
    const fetchMock = vi
      .spyOn(global, "fetch")
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true, policy: MOCK_POLICY }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({
          ok: true,
          policy: { ...MOCK_POLICY, fuji_rules: { ...MOCK_POLICY.fuji_rules, pii_check: false } },
        }),
      } as Response);

    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("FUJI Rules")).toBeInTheDocument();
    });

    // Toggle a rule to enable save button
    fireEvent.click(screen.getByRole("switch", { name: "PII Check (個人情報検査)" }));

    fireEvent.click(screen.getByText("ポリシーを保存"));

    await waitFor(() => {
      expect(screen.getByText("ポリシーを更新しました。")).toBeInTheDocument();
    });

    // PUT was called
    expect(fetchMock).toHaveBeenCalledTimes(2);
    const putCall = fetchMock.mock.calls[1];
    expect(putCall?.[1]?.method).toBe("PUT");
  });

  it("shows policy meta section", async () => {
    mockFetchPolicy();
    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("Policy Meta")).toBeInTheDocument();
      expect(screen.getByText("governance_v1")).toBeInTheDocument();
    });
  });

  it("resets draft to saved policy on reset button click", async () => {
    mockFetchPolicy();
    render(<GovernanceControlPage />);

    fireEvent.change(screen.getByLabelText("X-API-Key"), {
      target: { value: "test-key" },
    });
    fireEvent.click(screen.getByText("ポリシーを読み込む"));

    await waitFor(() => {
      expect(screen.getByText("FUJI Rules")).toBeInTheDocument();
    });

    // Toggle a rule
    fireEvent.click(screen.getByRole("switch", { name: "PII Check (個人情報検査)" }));
    expect(screen.getByText("未保存の変更があります")).toBeInTheDocument();

    // Click reset
    fireEvent.click(screen.getByText("リセット"));
    expect(screen.getByText("変更はありません。")).toBeInTheDocument();
  });
});
