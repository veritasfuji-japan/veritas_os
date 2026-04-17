import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../../../components/i18n-provider";
import { DecisionResultPanel } from "./decision-result-panel";

describe("DecisionResultPanel", () => {
  const baseResult = {
    ok: true,
    error: null,
    request_id: "req-test",
    version: "1.0",
    decision_status: "allow",
    gate_decision: "allow",
    business_decision: "REVIEW_REQUIRED",
    next_action: "ROUTE_TO_HUMAN_REVIEW",
    required_evidence: ["risk_assessment", "approval_ticket"],
    missing_evidence: ["approval_ticket"],
    human_review_required: true,
    active_posture: "strict",
    backend: "gpt-5.3-mini",
    verify_status: "verified",
    rejection_reason: null,
    chosen: { id: "a1", title: "Option A" },
    alternatives: [{ id: "b1", title: "Option B", value_score: 0.6 }],
    options: [],
    fuji: { decision_status: "allow" },
    gate: { decision_status: "allow" },
    evidence: [{ source: "doc", snippet: "s", confidence: 0.9 }],
    critique: [],
    debate: [],
    telos_score: 0.9,
    values: { total: 0.85, rationale: "High utility." },
    plan: null,
    planner: null,
    persona: {},
    memory_citations: [],
    memory_used_count: 0,
    trust_log: null,
    extras: {},
    meta: {},
    ai_disclosure: "",
    regulation_notice: "",
  };

  function renderPanel(viewerRole: "auditor" | "operator" | "developer" = "operator") {
    return render(
      <I18nProvider>
        <DecisionResultPanel result={baseResult as never} viewerRole={viewerRole} />
      </I18nProvider>,
    );
  }

  it("renders comparison table when alternatives exist", () => {
    renderPanel();
    const table = screen.getByRole("table", { name: /比較|comparison/i });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByText(/Chosen|採択/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/代替\s*1|Alt\s*1/)).toBeInTheDocument();
  });

  it("shows value score bars for chosen and alternatives", () => {
    renderPanel();
    expect(screen.getAllByText("85%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
  });

  it("does not render comparison table when no alternatives", () => {
    const noAlts = { ...baseResult, alternatives: [] };
    render(
      <I18nProvider>
        <DecisionResultPanel result={noAlts as never} />
      </I18nProvider>,
    );
    expect(screen.queryByRole("table", { name: /比較|comparison/i })).not.toBeInTheDocument();
    expect(screen.getByText(/No alternatives provided|代替案はありません/)).toBeInTheDocument();
  });

  it("shows dash for null value scores", () => {
    const noScores = {
      ...baseResult,
      values: { rationale: "No total" },
      alternatives: [{ id: "b1", title: "Option B" }],
    };
    render(
      <I18nProvider>
        <DecisionResultPanel result={noScores as never} />
      </I18nProvider>,
    );
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("renders auditor-focused detail block", () => {
    renderPanel("auditor");
    expect(screen.getByText(/監査人|Auditor/)).toBeInTheDocument();
    expect(screen.getByText(/human_review_required/)).toBeInTheDocument();
  });

  it("renders developer-focused detail block with runtime status contract", () => {
    renderPanel("developer");
    expect(screen.getByText(/開発者|Developer/)).toBeInTheDocument();
    expect(screen.getByText(/active posture/)).toBeInTheDocument();
    expect(screen.getByText("strict")).toBeInTheDocument();
    expect(screen.getByText("gpt-5.3-mini")).toBeInTheDocument();
    expect(screen.getByText("verified")).toBeInTheDocument();
  });

  it("dispatches bundle generation callback", () => {
    const bundleSpy = vi.fn();
    render(
      <I18nProvider>
        <DecisionResultPanel result={baseResult as never} onGenerateBundle={bundleSpy} />
      </I18nProvider>,
    );
    screen.getByRole("button", { name: /bundle/i }).click();
    expect(bundleSpy).toHaveBeenCalledTimes(1);
    expect(bundleSpy.mock.calls[0][0]).toMatchObject({
      requestId: "req-test",
      businessDecision: "REVIEW_REQUIRED",
      runtimeStatus: {
        activePosture: "strict",
        backend: "gpt-5.3-mini",
        verifyStatus: "verified",
      },
    });
  });
});
