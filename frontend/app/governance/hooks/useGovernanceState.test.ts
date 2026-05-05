import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";

vi.mock("../../../components/i18n-provider", () => ({
  useI18n: () => ({
    language: "en",
    t: (_ja: string, en: string) => en,
    tk: (k: string) => k,
    setLanguage: () => {},
  }),
}));

const mockFetch = vi.fn();
vi.mock("../../../lib/api-client", () => ({
  veritasFetch: (...args: unknown[]) => mockFetch(...args),
}));

const mockValidate = vi.fn();
vi.mock("../../../lib/api-validators", () => ({
  validateGovernancePolicyResponse: (...args: unknown[]) => mockValidate(...args),
}));

import { useGovernanceState } from "./useGovernanceState";

const MOCK_POLICY = {
  version: "v1.0",
  updated_at: "2026-01-01T00:00:00Z",
  updated_by: "admin",
  fuji_rules: {
    pii_check: true,
    self_harm_block: true,
    illicit_block: false,
    violence_review: true,
    minors_review: true,
    keyword_hard_block: true,
    keyword_soft_flag: false,
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
    include_fields: ["status"],
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
    human_review_ticket: "TICKET-123",
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
    replay_binding_required: false,
    partial_validation_default: "non_admissible",
    warning_only_until: "",
    timestamp_skew_tolerance_seconds: 5,
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
};

const setValidApprovals = (result: { current: ReturnType<typeof useGovernanceState> }): void => {
  act(() => {
    result.current.updateApprovalRecord(0, { reviewer: "reviewerA", signature: "sig-A" });
    result.current.updateApprovalRecord(1, { reviewer: "reviewerB", signature: "sig-B" });
  });
};

const approveDraft = async (result: { current: ReturnType<typeof useGovernanceState> }): Promise<void> => {
  act(() => { result.current.approveChanges(); });
  act(() => { result.current.pendingConfirm?.onConfirm(); });
  await waitFor(() => {
    expect(result.current.approvalRecords[0].decision).toBe("approved");
    expect(result.current.approvalRecords[1].decision).toBe("approved");
  });
};

describe("useGovernanceState", () => {
  beforeEach(() => {
    mockFetch.mockReset();
    mockValidate.mockReset();
  });

  it("initialises with correct defaults", () => {
    const { result } = renderHook(() => useGovernanceState());
    expect(result.current.savedPolicy).toBeNull();
    expect(result.current.draft).toBeNull();
    expect(result.current.selectedRole).toBe("admin");
    expect(result.current.loading).toBe(false);
    expect(result.current.hasChanges).toBe(false);
    expect(result.current.canApply).toBe(true);
    expect(result.current.canOperate).toBe(true);
  });

  it("fetchPolicy loads policy on success", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    expect(result.current.savedPolicy).not.toBeNull();
    expect(result.current.draft).not.toBeNull();
    expect(result.current.savedPolicy!.version).toBe("v1.0");
    expect(result.current.history.length).toBeGreaterThan(0);
    expect(result.current.trustLog.length).toBeGreaterThan(0);
  });

  it("fetchPolicy sets error on HTTP failure", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500 });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    expect(result.current.error).toContain("HTTP 500");
  });

  it("fetchPolicy sets error on validation failure", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    mockValidate.mockReturnValue({ ok: false });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    expect(result.current.error).toContain("validation failed");
  });

  it("fetchPolicy sets error on network exception", async () => {
    mockFetch.mockRejectedValue(new Error("Network failure"));

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    expect(result.current.error).toContain("Network error");
  });

  it("canApply/canOperate/canApprove depend on selectedRole", () => {
    const { result } = renderHook(() => useGovernanceState());

    act(() => { result.current.setSelectedRole("viewer"); });
    expect(result.current.canApply).toBe(false);
    expect(result.current.canOperate).toBe(false);
    expect(result.current.canApprove).toBe(false);

    act(() => { result.current.setSelectedRole("operator"); });
    expect(result.current.canApply).toBe(false);
    expect(result.current.canOperate).toBe(true);
    expect(result.current.canApprove).toBe(false);

    act(() => { result.current.setSelectedRole("admin"); });
    expect(result.current.canApply).toBe(true);
    expect(result.current.canOperate).toBe(true);
    expect(result.current.canApprove).toBe(true);
  });

  it("updateDraft modifies draft and sets approval_status to pending", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({
        ...prev,
        fuji_rules: { ...prev.fuji_rules, pii_check: false },
      }));
    });

    expect(result.current.draft!.fuji_rules.pii_check).toBe(false);
    expect(result.current.draft!.approval_status).toBe("pending");
    expect(result.current.hasChanges).toBe(true);
  });

  it("applyPolicy dry-run mode does not call PUT", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    mockFetch.mockClear();

    act(() => { result.current.applyPolicy("dry-run"); });
    // Confirm the pending action
    expect(result.current.pendingConfirm).not.toBeNull();
    await act(async () => { result.current.pendingConfirm!.onConfirm(); });

    // dry-run should not call veritasFetch for PUT
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.success).toContain("Dry-run");
  });

  it("rollback reverts draft to savedPolicy", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    // Make a change
    act(() => {
      result.current.updateDraft((prev) => ({
        ...prev,
        fuji_rules: { ...prev.fuji_rules, pii_check: false },
      }));
    });
    expect(result.current.hasChanges).toBe(true);

    // Rollback
    act(() => { result.current.rollback(); });
    expect(result.current.pendingConfirm).not.toBeNull();
    act(() => { result.current.pendingConfirm!.onConfirm(); });
    expect(result.current.hasChanges).toBe(false);
  });

  it("dismissConfirm clears pendingConfirm", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => { result.current.applyPolicy("dry-run"); });
    expect(result.current.pendingConfirm).not.toBeNull();
    act(() => { result.current.dismissConfirm(); });
    expect(result.current.pendingConfirm).toBeNull();
  });

  it("applyPolicy shadow mode does not call PUT", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    mockFetch.mockClear();

    act(() => { result.current.applyPolicy("shadow"); });
    expect(result.current.pendingConfirm).not.toBeNull();
    await act(async () => { result.current.pendingConfirm!.onConfirm(); });

    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.success).toContain("Shadow mode");
  });

  it("applyPolicy apply mode calls PUT and updates policy on success", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    const updatedPolicy = { ...MOCK_POLICY, version: "v2.0" };
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: updatedPolicy }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: updatedPolicy } });

    act(() => { result.current.applyPolicy("apply"); });
    expect(result.current.pendingConfirm).not.toBeNull();
    await act(async () => { result.current.pendingConfirm!.onConfirm(); });

    expect(mockFetch).toHaveBeenCalledWith(
      "/api/veritas/v1/governance/policy",
      expect.objectContaining({ method: "PUT" }),
    );
    const putRequest = mockFetch.mock.calls.at(-1)?.[1] as { body?: string };
    const payload = JSON.parse(putRequest.body ?? "{}");
    expect(payload.approvals).toHaveLength(2);
    expect(payload.approvals[0].reviewer).toBe("reviewerA");
    expect(payload.wat.issuance_mode).toBe("shadow_only");
    expect(payload.shadow_validation.partial_validation_default).toBe("non_admissible");
    expect(payload.revocation.mode).toBe("bounded_eventual_consistency");
    expect(payload).not.toHaveProperty("wat_settings");
    expect(result.current.success).toContain("applied");
    expect(result.current.savedPolicy!.version).toBe("v2.0");
  });

  it("applyPolicy apply mode sets error on HTTP failure", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    mockFetch.mockResolvedValue({ ok: false, status: 500 });

    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm!.onConfirm(); });

    expect(result.current.error).toContain("HTTP 500");
  });

  it("applyPolicy apply mode sets error on validation failure", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    mockValidate.mockReturnValue({ ok: false });

    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm!.onConfirm(); });

    expect(result.current.error).toContain("validation failed");
  });

  it("applyPolicy apply mode sets error on network failure", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });
    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    mockFetch.mockRejectedValue(new Error("Network failure"));

    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm!.onConfirm(); });

    expect(result.current.error).toContain("Apply failed");
  });



  it("invalidates approved record and draft status when reviewer is edited after approval", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    const reviewedAtBefore = result.current.approvalRecords[0].reviewed_at;
    act(() => {
      result.current.updateApprovalRecord(0, { reviewer: "reviewerA-updated" });
    });

    expect(result.current.approvalRecords[0].decision).toBe("pending");
    expect(result.current.approvalRecords[0].reviewed_at).toBeUndefined();
    expect(result.current.trustLog.some((entry) => entry.message.includes("re-approval required"))).toBe(true);
    expect(reviewedAtBefore).toBeDefined();
  });

  it("invalidates approved record when signature or reason is edited after approval", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    act(() => {
      result.current.updateApprovalRecord(0, { signature: "sig-A-updated" });
    });
    expect(result.current.approvalRecords[0].decision).toBe("pending");

    await approveDraft(result);
    act(() => {
      result.current.updateApprovalRecord(1, { reason: "reason-updated" });
    });
    expect(result.current.approvalRecords[1].decision).toBe("pending");
  });

  it("requires re-approval after approval metadata edits and refreshes reviewed_at", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);

    const firstReviewedAt = result.current.approvalRecords[0].reviewed_at;
    act(() => {
      result.current.updateApprovalRecord(0, { reviewer: "reviewerA-updated" });
    });
    expect(result.current.draft?.approval_status).toBe("pending");

    mockFetch.mockClear();
    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });
    expect(mockFetch).not.toHaveBeenCalled();

    act(() => {
      result.current.updateApprovalRecord(0, { signature: "sig-A-updated" });
    });
    await approveDraft(result);

    expect(result.current.approvalRecords[0].reviewed_at).toBeDefined();
    expect(result.current.approvalRecords[0].reviewed_at).not.toBe(firstReviewedAt);

    mockFetch.mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });
    mockFetch.mockClear();

    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });

    const applyCall = mockFetch.mock.calls.find((call) => call[0] === "/api/veritas/v1/governance/policy" && call[1]?.method === "PUT");
    expect(applyCall).toBeDefined();
    const payload = JSON.parse(applyCall[1].body as string) as { approvals: Array<{ reviewer: string; signature: string }> };
    expect(payload.approvals).toHaveLength(2);
    expect(payload.approvals[0].reviewer).toBe("reviewerA-updated");
  });

  it("approveChanges sets draft approval_status to approved", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    // Make a change first so hasChanges is true
    act(() => {
      result.current.updateDraft((prev) => ({
        ...prev,
        fuji_rules: { ...prev.fuji_rules, pii_check: false },
      }));
    });
    expect(result.current.hasChanges).toBe(true);
    setValidApprovals(result);

    act(() => { result.current.approveChanges(); });
    expect(result.current.pendingConfirm).not.toBeNull();
    act(() => { result.current.pendingConfirm!.onConfirm(); });

    expect(result.current.draft!.approval_status).toBe("approved");
    expect(result.current.approvalRecords[0].decision).toBe("approved");
    expect(result.current.approvalRecords[1].decision).toBe("approved");
    expect(result.current.success).toContain("approved");
  });

  it("rejectChanges sets draft approval_status to rejected", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    // Make a change first
    act(() => {
      result.current.updateDraft((prev) => ({
        ...prev,
        fuji_rules: { ...prev.fuji_rules, pii_check: false },
      }));
    });

    act(() => { result.current.rejectChanges(); });
    expect(result.current.pendingConfirm).not.toBeNull();
    act(() => { result.current.pendingConfirm!.onConfirm(); });

    expect(result.current.draft!.approval_status).toBe("rejected");
    expect(result.current.approvalRecords[0].decision).toBe("rejected");
    expect(result.current.approvalRecords[1].decision).toBe("rejected");
    expect(result.current.success).toContain("rejected");
  });

  it("approveChanges does nothing without changes", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => { result.current.approveChanges(); });
    expect(result.current.pendingConfirm).toBeNull();
  });

  it("rejectChanges does nothing without changes", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => { result.current.rejectChanges(); });
    expect(result.current.pendingConfirm).toBeNull();
  });

  it("draftApprovalStatus returns pending when there are changes", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({
        ...prev,
        fuji_rules: { ...prev.fuji_rules, pii_check: false },
      }));
    });

    expect(result.current.draftApprovalStatus).toBe("pending");
  });

  it("blocks apply when reviewers are duplicated", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
      result.current.updateApprovalRecord(0, { reviewer: "reviewerA", signature: "sig-A" });
      result.current.updateApprovalRecord(1, { reviewer: "reviewerB", signature: "sig-B" });
    });
    await approveDraft(result);
    act(() => {
      result.current.updateApprovalRecord(0, { reviewer: "dup" });
      result.current.updateApprovalRecord(1, { reviewer: "dup" });
    });
    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });

    expect(result.current.error).toContain("must be approved by two reviewers");
  });

  it("blocks apply when signatures are duplicated", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
      result.current.updateApprovalRecord(0, { reviewer: "reviewerA", signature: "sig-A" });
      result.current.updateApprovalRecord(1, { reviewer: "reviewerB", signature: "sig-B" });
    });
    await approveDraft(result);
    act(() => {
      result.current.updateApprovalRecord(0, { signature: "same" });
      result.current.updateApprovalRecord(1, { signature: "same" });
    });
    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });

    expect(result.current.error).toContain("must be approved by two reviewers");
  });

  it("blocks apply when draft is rejected", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
      result.current.updateApprovalRecord(0, { reviewer: "reviewerA", signature: "sig-A" });
      result.current.updateApprovalRecord(1, { reviewer: "reviewerB", signature: "sig-B" });
    });
    act(() => {
      result.current.rejectChanges();
    });
    act(() => { result.current.pendingConfirm?.onConfirm(); });

    setValidApprovals(result);
    mockFetch.mockClear();
    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });

    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.draft?.approval_status).toBe("rejected");
  });

  it("blocks apply when draft approval_status is pending", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    mockFetch.mockClear();

    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });

    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.error).toContain("must be approved by two reviewers");
  });

  it("apply payload includes only approved records and blocks with fewer than two approvals", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    act(() => {
      result.current.updateDraft((prev) => ({ ...prev, fuji_rules: { ...prev.fuji_rules, pii_check: false } }));
    });
    setValidApprovals(result);
    await approveDraft(result);
    act(() => {
      result.current.updateApprovalRecord(1, { decision: "pending" });
    });
    mockFetch.mockClear();
    act(() => { result.current.applyPolicy("apply"); });
    await act(async () => { result.current.pendingConfirm?.onConfirm(); });
    expect(mockFetch).not.toHaveBeenCalled();
    expect(result.current.error).toContain("two approved human approval records");
  });

  it("draftApprovalStatus returns draft when no draft loaded", () => {
    const { result } = renderHook(() => useGovernanceState());
    expect(result.current.draftApprovalStatus).toBe("draft");
  });

  it("changeCount reflects the number of changed fields", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    expect(result.current.changeCount).toBe(0);

    act(() => {
      result.current.updateDraft((prev) => ({
        ...prev,
        fuji_rules: { ...prev.fuji_rules, pii_check: false },
      }));
    });

    expect(result.current.changeCount).toBeGreaterThan(0);
  });

  it("risk calculations are derived correctly", async () => {
    mockFetch.mockResolvedValue({ ok: true, json: () => Promise.resolve({ policy: MOCK_POLICY }) });
    mockValidate.mockReturnValue({ ok: true, data: { policy: MOCK_POLICY } });

    const { result } = renderHook(() => useGovernanceState());
    await act(async () => {
      await result.current.fetchPolicy();
    });

    // currentRisk = ((deny_upper + max_risk_score) / 2) * 100 = ((1.0 + 0.85) / 2) * 100 = 92.5 → 93
    expect(result.current.currentRisk).toBe(93);
    expect(result.current.riskDrift).toBe(0); // no changes yet
  });
});
