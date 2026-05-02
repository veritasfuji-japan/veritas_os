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
    wat: { enabled: false, issuance_mode: "shadow_only", require_observable_digest: true, default_ttl_seconds: 300, signer_backend: "existing_signer", wat_metadata_retention_ttl_seconds: 7776000, wat_event_pointer_retention_ttl_seconds: 7776000, observable_digest_retention_ttl_seconds: 31536000, observable_digest_access_class: "restricted", observable_digest_ref: "separate_store://wat_observables", retention_policy_version: "wat_retention_v1", retention_enforced_at_write: true },
    psid: { enforcement_mode: "full_digest_only", display_length: 12 },
    shadow_validation: { enabled: true, partial_validation_default: "non_admissible", warning_only_until: "", timestamp_skew_tolerance_seconds: 5, replay_binding_required: false, replay_binding_escalation_threshold: 4, partial_validation_requires_confirmation: true },
    revocation: { enabled: true, mode: "bounded_eventual_consistency", alert_target_seconds: 30, convergence_target_p95_seconds: 60, degrade_on_pending: true, revocation_confirmation_required: true, auto_escalate_confirmed_revocations: false },
    drift_scoring: { policy_weight: 0.4, signature_weight: 0.3, observable_weight: 0.2, temporal_weight: 0.1, healthy_threshold: 0.2, critical_threshold: 0.5 },
    bind_adjudication: { missing_signal_default: "block", drift_required: true, ttl_required: false, approval_freshness_required: false, rollback_on_apply_failure: false },
    operator_verbosity: "minimal",
    updated_at: "2026-01-01T00:00:00+00:00",
    updated_by: "admin",
  },
};

describe("Governance control plane", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string | URL | Request) => {
        const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;

        if (url.includes("/api/auth/session")) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ ok: true, role: "admin" }),
          };
        }

        return {
          ok: true,
          status: 200,
          json: async () => policyResponse,
        };
      }),
    );
    let seq = 0;
    vi.stubGlobal("crypto", { randomUUID: () => `uuid-${seq++}` });
    vi.stubGlobal("confirm", vi.fn().mockReturnValue(true));
  });

  it("renders policy metadata after loading", async () => {
    render(<GovernanceControlPage />);
    const loadPolicyButton = screen.getByRole("button", { name: "ポリシーを読み込む" });
    await waitFor(() => expect(loadPolicyButton).toBeEnabled());
    fireEvent.click(loadPolicyButton);

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
    const loadPolicyButton = screen.getByRole("button", { name: "ポリシーを読み込む" });
    await waitFor(() => expect(loadPolicyButton).toBeEnabled());
    fireEvent.click(loadPolicyButton);

    await waitFor(() => expect(screen.getByRole("button", { name: "適用" })).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText("role"), { target: { value: "viewer" } });
    expect(screen.getByRole("button", { name: "適用" })).toBeDisabled();
  });
});
