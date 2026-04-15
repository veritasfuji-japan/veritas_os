import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
    alternatives: [
      { id: "b1", title: "Option B", value_score: 0.6 },
    ],
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

  it("renders comparison table when alternatives exist", () => {
    render(<DecisionResultPanel result={baseResult as never} />);
    const table = screen.getByRole("table", { name: /chosen vs alternatives comparison/i });
    expect(table).toBeInTheDocument();
    expect(screen.getAllByText("Chosen").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("Alt 1")).toBeInTheDocument();
  });

  it("shows value score bars for chosen and alternatives", () => {
    render(<DecisionResultPanel result={baseResult as never} />);
    // Chosen should show 85% and alternative 60%
    expect(screen.getAllByText("85%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("60%").length).toBeGreaterThan(0);
  });

  it("does not render comparison table when no alternatives", () => {
    const noAlts = { ...baseResult, alternatives: [] };
    render(<DecisionResultPanel result={noAlts as never} />);
    expect(screen.queryByRole("table", { name: /chosen vs alternatives comparison/i })).not.toBeInTheDocument();
    expect(screen.getByText("No alternatives provided.")).toBeInTheDocument();
  });

  it("shows dash for null value scores", () => {
    const noScores = {
      ...baseResult,
      values: { rationale: "No total" },
      alternatives: [{ id: "b1", title: "Option B" }],
    };
    render(<DecisionResultPanel result={noScores as never} />);
    // Should render dash placeholders for missing scores
    const dashes = screen.getAllByText("-");
    expect(dashes.length).toBeGreaterThan(0);
  });

  it("renders rejected reasons section", () => {
    render(<DecisionResultPanel result={baseResult as never} />);
    expect(screen.getByText("Rejected reasons")).toBeInTheDocument();
    expect(screen.getByText("FUJI block:")).toBeInTheDocument();
  });

  it("renders separated public decision schema fields", () => {
    render(<DecisionResultPanel result={baseResult as never} />);
    expect(screen.getByText("Public decision output")).toBeInTheDocument();
    expect(screen.getByText("gate_decision:")).toBeInTheDocument();
    expect(screen.getByText("allow")).toBeInTheDocument();
    expect(screen.getByText("business_decision:")).toBeInTheDocument();
    expect(screen.getAllByText("REVIEW_REQUIRED").length).toBeGreaterThan(0);
    expect(screen.getByText("ROUTE_TO_HUMAN_REVIEW")).toBeInTheDocument();
    expect(screen.getByText("不足証拠 / Missing evidence")).toBeInTheDocument();
    expect(screen.getByText("次に実行するアクション / Next action")).toBeInTheDocument();
    expect(screen.getByText("required_evidence:")).toBeInTheDocument();
    expect(screen.getByText("risk_assessment, approval_ticket")).toBeInTheDocument();
    expect(screen.getByText("human_review_required:")).toBeInTheDocument();
    expect(screen.getByText("true")).toBeInTheDocument();
  });

  it("does not present gate allow as case approval in the public decision meaning", () => {
    render(<DecisionResultPanel result={baseResult as never} />);
    expect(screen.getByText("response generation allowed (not case approval)")).toBeInTheDocument();
  });

  it("shows auditor and developer focused detail blocks", () => {
    render(<DecisionResultPanel result={baseResult as never} />);
    expect(screen.getByText("監査人向け")).toBeInTheDocument();
    expect(screen.getByText("開発者向け")).toBeInTheDocument();
    expect(screen.getByText("active posture:")).toBeInTheDocument();
    expect(screen.getByText("strict")).toBeInTheDocument();
    expect(screen.getByText("backend:")).toBeInTheDocument();
    expect(screen.getByText("gpt-5.3-mini")).toBeInTheDocument();
    expect(screen.getByText("verify status:")).toBeInTheDocument();
    expect(screen.getByText("verified")).toBeInTheDocument();
  });
});
