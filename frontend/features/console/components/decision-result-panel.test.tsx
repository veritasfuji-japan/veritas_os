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

  function renderPanel(
    viewerRole: "auditor" | "operator" | "developer" = "operator",
    language: "ja" | "en" = "ja",
  ) {
    window.localStorage.setItem("veritas_language", language);
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

  it("renders bind-phase block with decision-vs-bind distinction and reason", () => {
    const bindResult = {
      ...baseResult,
      gate_decision: "allow",
      bind_outcome: "BLOCKED",
      bind_failure_reason: "authority denied",
      bind_reason_code: "AUTHORITY_DENIED",
      bind_receipt_id: "br-11",
      execution_intent_id: "ei-11",
      authority_check_result: { passed: false },
      constraint_check_result: { passed: true },
      drift_check_result: { result: "stable" },
      risk_check_result: { result: "elevated" },
    };
    render(
      <I18nProvider>
        <DecisionResultPanel result={bindResult as never} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(screen.getByText(/Bind-phase governance|Bindフェーズ統治/)).toBeInTheDocument();
    expect(screen.getByText(/Decision phase:/)).toBeInTheDocument();
    expect(screen.getByText(/Bind phase:/)).toBeInTheDocument();
    expect(screen.getByText("BLOCKED")).toBeInTheDocument();
    expect(screen.getByText("authority denied")).toBeInTheDocument();
    expect(screen.getByText("AUTHORITY_DENIED")).toBeInTheDocument();
    expect(screen.getByText("FAIL")).toBeInTheDocument();
    expect(screen.getByText("PASS")).toBeInTheDocument();
  });

  it.each([
    "COMMITTED",
    "BLOCKED",
    "ESCALATED",
    "ROLLED_BACK",
    "APPLY_FAILED",
    "SNAPSHOT_FAILED",
    "PRECONDITION_FAILED",
  ])(
    "renders bind outcome badge for %s",
    (outcome) => {
      render(
        <I18nProvider>
          <DecisionResultPanel result={{ ...baseResult, bind_outcome: outcome } as never} viewerRole="operator" />
        </I18nProvider>,
      );
      expect(screen.getByText(outcome)).toBeInTheDocument();
    },
  );

  it("shows unsupported bind outcomes without collapsing to UNKNOWN", () => {
    render(
      <I18nProvider>
        <DecisionResultPanel result={{ ...baseResult, bind_outcome: "CUSTOM_STATE" } as never} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(screen.getByText("CUSTOM_STATE")).toBeInTheDocument();
    expect(screen.getByText(/Non-canonical bind outcome reported by runtime contract/)).toBeInTheDocument();
  });

  it("keeps legacy decision view stable when bind fields are absent", () => {
    const legacyResult = { ...baseResult };
    render(
      <I18nProvider>
        <DecisionResultPanel result={legacyResult as never} viewerRole="operator" />
      </I18nProvider>,
    );
    expect(screen.getByText(/final decision|最終判断/i)).toBeInTheDocument();
    expect(screen.getAllByText(/gate_decision/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/business_decision/i).length).toBeGreaterThan(0);
  });

  it("renders formation transition refusal card", () => {
    const refusedResult = {
      ...baseResult,
      transition_refusal: {
        transition_status: "structurally_refused",
        reason_code: "NON_PROMOTABLE_LINEAGE",
        invariant_id: "BIND_ELIGIBLE_ARTIFACT_CANNOT_EMERGE_FROM_NON_PROMOTABLE_LINEAGE",
        source_promotability_status: "non_promotable",
        execution_intent_created: false,
        bind_receipt_created: false,
        concise_rationale: "ExecutionIntent cannot be constructed from a non-promotable pre-bind formation lineage.",
      },
      actionability_status: "formation_transition_refused",
      actionability_block_reason: "FORMATION_TRANSITION_REFUSED",
      actionability_refusal_type: "pre_bind_formation_transition_refusal",
      recovery_action: "RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE",
      recovery_reason: "The refused artifact is not bind-retryable; reconstruct the decision from an eligible formation lineage.",
      execution_intent_id: null,
      bound_execution_intent_id: null,
      bind_receipt_id: null,
      bind_receipt: null,
      human_review_required: true,
    };
    window.localStorage.setItem("veritas_language", "en");
    render(<I18nProvider><DecisionResultPanel result={refusedResult as never} /></I18nProvider>);
    expect(screen.getByText("Formation Transition Refused")).toBeInTheDocument();
    expect(screen.getAllByText(/This decision was stopped before bind because its formation lineage is not eligible for execution/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Do not retry bind/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/Rebuild the decision from eligible evidence and formation history/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("NON_PROMOTABLE_LINEAGE")).toBeInTheDocument();
    expect(screen.getByText("FORMATION_TRANSITION_REFUSED")).toBeInTheDocument();
    expect(screen.getByText("pre_bind_formation_transition_refusal")).toBeInTheDocument();
    expect(screen.getByText("RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE")).toBeInTheDocument();
    expect(screen.getAllByText("not created").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("no")).toBeInTheDocument();
  });

  it("renders card when actionability_status alone indicates refusal", () => {
    const refusedResult = {
      ...baseResult,
      transition_refusal: null,
      actionability_status: "formation_transition_refused",
      execution_intent_id: null,
      bind_receipt_id: null,
      human_review_required: true,
    };
    window.localStorage.setItem("veritas_language", "en");
    render(<I18nProvider><DecisionResultPanel result={refusedResult as never} /></I18nProvider>);
    expect(screen.getByText("Formation Transition Refused")).toBeInTheDocument();
    expect(screen.getByText("NON_PROMOTABLE_LINEAGE")).toBeInTheDocument();
    expect(screen.getByText("RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE")).toBeInTheDocument();
  });

  it("does not render card when transition is allowed", () => {
    const allowedResult = {
      ...baseResult,
      transition_refusal: null,
      actionability_status: "reviewable_only",
    };
    window.localStorage.setItem("veritas_language", "en");
    render(<I18nProvider><DecisionResultPanel result={allowedResult as never} /></I18nProvider>);
    expect(screen.queryByText("Formation Transition Refused")).not.toBeInTheDocument();
  });

  it("does not present bind retry wording in formation refusal card", () => {
    const refusedResult = {
      ...baseResult,
      actionability_status: "formation_transition_refused",
      transition_refusal: { transition_status: "structurally_refused" },
    };
    window.localStorage.setItem("veritas_language", "en");
    render(<I18nProvider><DecisionResultPanel result={refusedResult as never} /></I18nProvider>);
    const refusalCard = screen.getByText("Formation Transition Refused").closest("article");
    expect(refusalCard).toBeInTheDocument();
    expect(refusalCard).not.toHaveTextContent("Retry bind");
    expect(refusalCard).not.toHaveTextContent("Re-run bind");
    expect(refusalCard).not.toHaveTextContent("Bind failed");
    expect(refusalCard).not.toHaveTextContent("Bind blocked");
  });

  it("renders with partial transition_refusal payload without crashing", () => {
    const partialResult = {
      ...baseResult,
      transition_refusal: {
        transition_status: "structurally_refused",
      },
      actionability_status: "formation_transition_refused",
      execution_intent_id: null,
      bind_receipt_id: null,
    };
    window.localStorage.setItem("veritas_language", "en");
    render(<I18nProvider><DecisionResultPanel result={partialResult as never} /></I18nProvider>);
    expect(screen.getByText("Formation Transition Refused")).toBeInTheDocument();
    expect(screen.getByText("NON_PROMOTABLE_LINEAGE")).toBeInTheDocument();
    expect(screen.getByText("RECONSTRUCT_FROM_ELIGIBLE_FORMATION_LINEAGE")).toBeInTheDocument();
  });

  it("renders formation refusal card in Japanese", () => {
    const refusedResult = {
      ...baseResult,
      actionability_status: "formation_transition_refused",
      transition_refusal: { transition_status: "structurally_refused" },
      execution_intent_id: null,
      bind_receipt_id: null,
      human_review_required: true,
    };
    window.localStorage.setItem("veritas_language", "ja");
    render(<I18nProvider><DecisionResultPanel result={refusedResult as never} /></I18nProvider>);
    expect(screen.getByText("形成遷移が拒否されました")).toBeInTheDocument();
    expect(screen.getAllByText(/この判断は、実行候補として成立しない形成履歴だったため、bind 前に止められました/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/bind を再実行しても回復できません/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/判断材料と形成履歴を見直し/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("未作成").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("いいえ")).toBeInTheDocument();
    expect(screen.getByText("はい")).toBeInTheDocument();
  });
});
