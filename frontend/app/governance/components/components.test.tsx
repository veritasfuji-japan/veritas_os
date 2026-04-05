import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

// ── Mocks ──────────────────────────────────────────────────────────────────────

vi.mock("../../../components/i18n-provider", () => ({
  useI18n: () => ({
    language: "en",
    t: (_ja: string, en: string) => en,
    tk: (k: string) => k,
    setLanguage: () => {},
  }),
}));

vi.mock("@veritas/design-system", () => ({
  Card: ({ children, title }: { children: React.ReactNode; title?: string }) => (
    <div data-testid={`card-${title}`}>
      {title && <h3>{title}</h3>}
      {children}
    </div>
  ),
}));

vi.mock("../../../components/ui", () => ({
  StatusBadge: ({ label }: { label: string }) => (
    <span data-testid="status-badge">{label}</span>
  ),
}));

const mockCollectChanges = vi.fn(() => [] as DiffChange[]);
vi.mock("../helpers", () => ({
  collectChanges: (...args: unknown[]) => mockCollectChanges(...args),
}));

// ── Imports (after mocks) ──────────────────────────────────────────────────────

import { ToggleRow } from "./ToggleRow";
import { RiskImpactGauge } from "./RiskImpactGauge";
import { ChangeHistory } from "./ChangeHistory";
import { TrustLogStream } from "./TrustLogStream";
import { ApplyFlow } from "./ApplyFlow";
import { ApprovalWorkflow } from "./ApprovalWorkflow";
import { PolicyMetaPanel } from "./PolicyMetaPanel";
import { DiffPreview } from "./DiffPreview";
import { FujiRulesEditor } from "./FujiRulesEditor";

// ── Types ──────────────────────────────────────────────────────────────────────

import type { HistoryEntry, TrustLogEntry, DiffChange } from "../governance-types";

// ── Shared fixtures ────────────────────────────────────────────────────────────

const MOCK_DRAFT = {
  version: "v1.0",
  draft_version: "v1.1",
  effective_at: "2026-01-01",
  last_applied: "2026-01-01",
  approval_status: "pending" as const,
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
  updated_at: "2026-01-01T00:00:00Z",
};

// ── ToggleRow ──────────────────────────────────────────────────────────────────

describe("ToggleRow", () => {
  it("renders label and switch role", () => {
    render(<ToggleRow label="My Toggle" checked={false} onChange={() => {}} />);
    expect(screen.getByText("My Toggle")).toBeTruthy();
    expect(screen.getByRole("switch")).toBeTruthy();
  });

  it("calls onChange with toggled value on click", () => {
    const onChange = vi.fn();
    render(<ToggleRow label="Toggle" checked={false} onChange={onChange} />);
    fireEvent.click(screen.getByRole("switch"));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("is disabled when disabled prop is true", () => {
    const onChange = vi.fn();
    render(<ToggleRow label="Toggle" checked={true} onChange={onChange} disabled />);
    const btn = screen.getByRole("switch");
    expect(btn).toBeDisabled();
    fireEvent.click(btn);
    expect(onChange).not.toHaveBeenCalled();
  });
});

// ── RiskImpactGauge ────────────────────────────────────────────────────────────

describe("RiskImpactGauge", () => {
  it("renders current, pending, drift values", () => {
    render(<RiskImpactGauge current={60} pending={40} drift={3} />);
    expect(screen.getByText("60%")).toBeTruthy();
    expect(screen.getByText("40%")).toBeTruthy();
    expect(screen.getByText("+3% from baseline")).toBeTruthy();
  });

  it("shows danger styling for values > 75", () => {
    render(<RiskImpactGauge current={80} pending={90} drift={0} />);
    const currentLabel = screen.getByText("80%");
    expect(currentLabel.className).toContain("text-danger");
  });

  it("shows success styling for values <= 50", () => {
    render(<RiskImpactGauge current={30} pending={20} drift={0} />);
    const currentLabel = screen.getByText("30%");
    expect(currentLabel.className).toContain("text-success");
  });

  it("shows positive drift with + prefix", () => {
    render(<RiskImpactGauge current={50} pending={50} drift={10} />);
    expect(screen.getByText("+10% from baseline")).toBeTruthy();
  });
});

// ── ChangeHistory ──────────────────────────────────────────────────────────────

describe("ChangeHistory", () => {
  it("renders empty state message when no entries", () => {
    render(<ChangeHistory entries={[]} />);
    expect(
      screen.getByText("Change history will appear after policy operations."),
    ).toBeTruthy();
  });

  it("renders entries with action badges", () => {
    const entries: HistoryEntry[] = [
      { id: "1", action: "apply", actor: "admin", at: "2026-01-01", summary: "Applied v1" },
      { id: "2", action: "rollback", actor: "operator", at: "2026-01-02", summary: "Rolled back" },
    ];
    render(<ChangeHistory entries={entries} />);
    expect(screen.getByText("apply")).toBeTruthy();
    expect(screen.getByText("rollback")).toBeTruthy();
    expect(screen.getByText(/Applied v1/)).toBeTruthy();
    expect(screen.getByText(/Rolled back/)).toBeTruthy();
  });
});

// ── TrustLogStream ─────────────────────────────────────────────────────────────

describe("TrustLogStream", () => {
  it("renders empty state message when no entries", () => {
    render(<TrustLogStream entries={[]} />);
    expect(
      screen.getByText("Stream events will appear after loading a policy."),
    ).toBeTruthy();
  });

  it("renders entries with severity badges", () => {
    const entries: TrustLogEntry[] = [
      { id: "1", at: "12:00", message: "Policy loaded", severity: "info" },
      { id: "2", at: "12:01", message: "Risk spike", severity: "warning" },
      { id: "3", at: "12:02", message: "Policy violation", severity: "policy" },
    ];
    render(<TrustLogStream entries={entries} />);
    expect(screen.getByText("info")).toBeTruthy();
    expect(screen.getByText("warning")).toBeTruthy();
    expect(screen.getByText("policy")).toBeTruthy();
    expect(screen.getByText("Policy loaded")).toBeTruthy();
    expect(screen.getByText("Risk spike")).toBeTruthy();
  });
});

// ── ApplyFlow ──────────────────────────────────────────────────────────────────

describe("ApplyFlow", () => {
  it("renders all 4 buttons", () => {
    render(
      <ApplyFlow
        hasChanges={true}
        saving={false}
        canApply={true}
        canOperate={true}
        draftApprovalStatus="approved"
        onApply={() => {}}
        onRollback={() => {}}
      />,
    );
    expect(screen.getByText("apply")).toBeTruthy();
    expect(screen.getByText("dry-run")).toBeTruthy();
    expect(screen.getByText("shadow mode")).toBeTruthy();
    expect(screen.getByText("rollback")).toBeTruthy();
  });

  it("disables apply/rollback when canApply is false and shows RBAC warning", () => {
    render(
      <ApplyFlow
        hasChanges={true}
        saving={false}
        canApply={false}
        canOperate={true}
        draftApprovalStatus="approved"
        onApply={() => {}}
        onRollback={() => {}}
      />,
    );
    expect(screen.getByText("apply")).toBeDisabled();
    expect(screen.getByText("rollback")).toBeDisabled();
    expect(
      screen.getByText("RBAC: apply/rollback requires admin role."),
    ).toBeTruthy();
  });

  it("calls onApply with correct mode", () => {
    const onApply = vi.fn();
    render(
      <ApplyFlow
        hasChanges={true}
        saving={false}
        canApply={true}
        canOperate={true}
        draftApprovalStatus="approved"
        onApply={onApply}
        onRollback={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("dry-run"));
    expect(onApply).toHaveBeenCalledWith("dry-run");

    fireEvent.click(screen.getByText("apply"));
    expect(onApply).toHaveBeenCalledWith("apply");
  });

  it("shows approval info text when hasChanges and status != approved", () => {
    render(
      <ApplyFlow
        hasChanges={true}
        saving={false}
        canApply={true}
        canOperate={true}
        draftApprovalStatus="pending"
        onApply={() => {}}
        onRollback={() => {}}
      />,
    );
    expect(
      screen.getByText(
        "Approval is required before apply. dry-run / shadow can be executed before approval.",
      ),
    ).toBeTruthy();
  });
});

// ── ApprovalWorkflow ───────────────────────────────────────────────────────────

describe("ApprovalWorkflow", () => {
  it("renders approval status badge and change count", () => {
    render(
      <ApprovalWorkflow
        draftApprovalStatus="pending"
        changeCount={3}
        canApprove={true}
        ticketId="TICKET-1"
        approverIdentityBinding={true}
        onApprove={() => {}}
        onReject={() => {}}
      />,
    );
    expect(screen.getByTestId("status-badge")).toBeTruthy();
    expect(screen.getByTestId("status-badge").textContent).toBe("pending");
    expect(screen.getByText("3 change(s) awaiting approval")).toBeTruthy();
  });

  it("calls onApprove on approve button click", () => {
    const onApprove = vi.fn();
    render(
      <ApprovalWorkflow
        draftApprovalStatus="pending"
        changeCount={1}
        canApprove={true}
        ticketId="T-1"
        approverIdentityBinding={false}
        onApprove={onApprove}
        onReject={() => {}}
      />,
    );
    fireEvent.click(screen.getByText("approve"));
    expect(onApprove).toHaveBeenCalledTimes(1);
  });

  it("disables buttons when canApprove is false and shows RBAC warning", () => {
    render(
      <ApprovalWorkflow
        draftApprovalStatus="pending"
        changeCount={1}
        canApprove={false}
        ticketId="T-1"
        approverIdentityBinding={false}
        onApprove={() => {}}
        onReject={() => {}}
      />,
    );
    expect(screen.getByText("approve")).toBeDisabled();
    expect(screen.getByText("reject")).toBeDisabled();
    expect(
      screen.getByText("RBAC: approve/reject requires admin role."),
    ).toBeTruthy();
  });

  it("shows blocked warning when approval is blocked", () => {
    render(
      <ApprovalWorkflow
        draftApprovalStatus="rejected"
        changeCount={1}
        canApprove={true}
        ticketId="T-1"
        approverIdentityBinding={false}
        onApprove={() => {}}
        onReject={() => {}}
      />,
    );
    expect(
      screen.getByText(
        "Approval is blocked. To avoid showing risky changes as safe, do not apply this draft while unapproved.",
      ),
    ).toBeTruthy();
  });
});

// ── PolicyMetaPanel ────────────────────────────────────────────────────────────

describe("PolicyMetaPanel", () => {
  it("renders current version and draft version", () => {
    render(
      <PolicyMetaPanel
        savedPolicy={MOCK_DRAFT as any}
        draft={MOCK_DRAFT as any}
        draftApprovalStatus="pending"
        hasChanges={false}
        changeCount={0}
      />,
    );
    expect(screen.getByText("Current Version")).toBeTruthy();
    expect(screen.getByText("Draft Version")).toBeTruthy();
    expect(screen.getByText("v1.0")).toBeTruthy();
    expect(screen.getByText("v1.1")).toBeTruthy();
  });

  it("shows unapplied changes warning when hasChanges is true", () => {
    render(
      <PolicyMetaPanel
        savedPolicy={MOCK_DRAFT as any}
        draft={MOCK_DRAFT as any}
        draftApprovalStatus="pending"
        hasChanges={true}
        changeCount={5}
      />,
    );
    expect(
      screen.getByText("5 unapplied change(s). Approve before applying."),
    ).toBeTruthy();
  });
});

// ── DiffPreview ────────────────────────────────────────────────────────────────

describe("DiffPreview", () => {
  beforeEach(() => {
    mockCollectChanges.mockReset();
  });

  it("shows 'No changes.' when before and after are same/null", () => {
    mockCollectChanges.mockReturnValue([]);
    render(<DiffPreview before={null} after={null} />);
    expect(screen.getByText("No changes.")).toBeTruthy();
  });

  it("renders grouped diff changes", () => {
    const changes: DiffChange[] = [
      { path: "fuji_rules.pii_check", old: "true", next: "false", category: "rule" },
      { path: "risk_thresholds.allow_upper", old: "0.4", next: "0.5", category: "threshold" },
    ];
    mockCollectChanges.mockReturnValue(changes);

    render(<DiffPreview before={MOCK_DRAFT as any} after={MOCK_DRAFT as any} />);
    expect(screen.getByText("2 change(s) detected")).toBeTruthy();
    expect(screen.getByText("fuji_rules.pii_check")).toBeTruthy();
    expect(screen.getByText("risk_thresholds.allow_upper")).toBeTruthy();
  });

  it("shows high-impact warning for threshold/escalation changes", () => {
    const changes: DiffChange[] = [
      { path: "risk_thresholds.allow_upper", old: "0.4", next: "0.5", category: "threshold" },
      { path: "auto_stop.max_risk_score", old: "0.85", next: "0.9", category: "escalation" },
    ];
    mockCollectChanges.mockReturnValue(changes);

    render(<DiffPreview before={MOCK_DRAFT as any} after={MOCK_DRAFT as any} />);
    expect(
      screen.getByText(
        "2 high-impact change(s): risk threshold and auto-stop updates require re-evaluation before approval.",
      ),
    ).toBeTruthy();
  });
});

// ── FujiRulesEditor ────────────────────────────────────────────────────────────

describe("FujiRulesEditor", () => {
  it("renders FUJI rule toggle labels", () => {
    render(
      <FujiRulesEditor
        draft={MOCK_DRAFT as any}
        isViewer={false}
        onUpdate={() => {}}
      />,
    );
    expect(screen.getByText("PII Check")).toBeTruthy();
    expect(screen.getByText("Self-Harm Block")).toBeTruthy();
    expect(screen.getByText("Illicit Block")).toBeTruthy();
    expect(screen.getByText("Violence Review")).toBeTruthy();
    expect(screen.getByText("Minors Review")).toBeTruthy();
    expect(screen.getByText("Keyword Hard Block")).toBeTruthy();
    expect(screen.getByText("Keyword Soft Flag")).toBeTruthy();
    expect(screen.getByText("LLM Safety Head")).toBeTruthy();
  });

  it("toggles are disabled when isViewer is true", () => {
    render(
      <FujiRulesEditor
        draft={MOCK_DRAFT as any}
        isViewer={true}
        onUpdate={() => {}}
      />,
    );
    const switches = screen.getAllByRole("switch");
    switches.forEach((sw) => {
      expect(sw).toBeDisabled();
    });
  });

  it("calls onUpdate when a toggle is clicked", () => {
    const onUpdate = vi.fn();
    render(
      <FujiRulesEditor
        draft={MOCK_DRAFT as any}
        isViewer={false}
        onUpdate={onUpdate}
      />,
    );
    // Click the "Illicit Block" toggle (which is currently false)
    const illicitToggle = screen.getByLabelText("Illicit Block");
    fireEvent.click(illicitToggle);
    expect(onUpdate).toHaveBeenCalledTimes(1);
    // onUpdate receives an updater function
    expect(typeof onUpdate.mock.calls[0][0]).toBe("function");
  });
});
