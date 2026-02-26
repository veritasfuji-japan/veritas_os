import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import DecisionConsolePage from "./page";

describe("DecisionConsolePage", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders pipeline stages in fixed order", () => {
    render(<DecisionConsolePage />);

    expect(screen.getByText("1.", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("Evidence")).toBeInTheDocument();
    expect(screen.getByText("TrustLog")).toBeInTheDocument();
  });


  it("renders structured sections from decide response", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ok: true,
        error: null,
        request_id: "req-001",
        version: "1.0",
        decision_status: "allow",
        rejection_reason: null,
        chosen: { id: "a1" },
        alternatives: [{ id: "a1" }],
        options: [{ id: "a1" }],
        fuji: { decision_status: "allow" },
        gate: { decision_status: "allow" },
        evidence: [{ source: "doc", snippet: "s", confidence: 0.9 }],
        critique: [],
        debate: [],
        telos_score: 0.9,
        values: { utility: 0.8 },
        plan: null,
        planner: null,
        persona: {},
        memory_citations: [{ id: "m1" }],
        memory_used_count: 1,
        trust_log: null,
        extras: { raw: true },
      }),
    } as Response);

    render(<DecisionConsolePage />);
    fireEvent.change(screen.getByPlaceholderText("メッセージを入力"), {
      target: { value: "A/B test" },
    });

    fireEvent.click(screen.getByRole("button", { name: "送信" }));

    await waitFor(() => {
      expect(screen.getByText("decision_status / chosen")).toBeInTheDocument();
      expect(screen.getByText("memory_citations / memory_used_count")).toBeInTheDocument();
      expect(screen.getByText("Cost-Benefit Analytics")).toBeInTheDocument();
      expect(screen.getByText("Total Token Cost")).toBeInTheDocument();
      expect(screen.getByRole("list", { name: "chat messages" })).toBeInTheDocument();
      expect(screen.getByText("user")).toBeInTheDocument();
      expect(screen.getByText("assistant")).toBeInTheDocument();
    });
  });



  it("shows governance drift alert when threshold is exceeded", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ok: true,
        error: null,
        request_id: "req-003",
        version: "1.0",
        decision_status: "modify",
        rejection_reason: null,
        chosen: { id: "a3" },
        alternatives: [{ id: "a3" }],
        options: [{ id: "a3" }],
        fuji: { decision_status: "allow" },
        gate: { decision_status: "modify", risk: 0.8 },
        evidence: [{ source: "doc", snippet: "s", confidence: 0.9 }],
        critique: [],
        debate: [],
        telos_score: 0.6,
        values: { valuecore_drift: 12.5 },
        plan: null,
        planner: null,
        persona: {},
        memory_citations: [],
        memory_used_count: 0,
        trust_log: null,
        extras: {},
      }),
    } as Response);

    render(<DecisionConsolePage />);
    fireEvent.change(screen.getByPlaceholderText("メッセージを入力"), {
      target: { value: "governance drift" },
    });

    fireEvent.click(screen.getByRole("button", { name: "送信" }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "1 Issue" })).toBeInTheDocument();
      expect(screen.getByText("Drift Alert")).toBeInTheDocument();
      expect(screen.getByText("ValueCoreの乖離が閾値を超えました。レビューを推奨します。")).toBeInTheDocument();
    });
  });

  it("uses backend provided cost_benefit_analytics when available", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ok: true,
        error: null,
        request_id: "req-002",
        version: "1.0",
        decision_status: "allow",
        rejection_reason: null,
        chosen: { id: "a2", uncertainty: 0.45 },
        alternatives: [{ id: "a2" }],
        options: [{ id: "a2" }],
        fuji: { decision_status: "allow" },
        gate: { decision_status: "allow", risk: 0.4 },
        evidence: [{ source: "doc", snippet: "s", confidence: 0.9 }],
        critique: [{ issue: "x" }],
        debate: [{ stance: "pro" }],
        telos_score: 0.8,
        values: { utility: 0.7 },
        plan: null,
        planner: null,
        persona: {},
        memory_citations: [],
        memory_used_count: 0,
        trust_log: null,
        extras: {
          cost_benefit_analytics: {
            steps: [
              {
                name: "Debate",
                executed: true,
                uncertainty_before: 0.45,
                uncertainty_after: 0.28,
                token_cost: 520,
              },
            ],
            total_token_cost: 520,
            uncertainty_reduction: 0.17,
          },
        },
      }),
    } as Response);

    render(<DecisionConsolePage />);
    fireEvent.change(screen.getByPlaceholderText("メッセージを入力"), {
      target: { value: "A/B test" },
    });

    fireEvent.click(screen.getByRole("button", { name: "送信" }));

    await waitFor(() => {
      expect(screen.getAllByText("Debate").length).toBeGreaterThan(1);
      expect(screen.getAllByText("520").length).toBeGreaterThan(1);
      expect(screen.getAllByText("17.0%").length).toBeGreaterThan(1);
    });
  });

  it("renders FUJI Gate status and expandable steps", async () => {
    vi.spyOn(global, "fetch").mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ok: true,
        error: null,
        request_id: "req-004",
        version: "1.0",
        decision_status: "modify",
        rejection_reason: "needs redaction",
        chosen: { id: "a4" },
        alternatives: [{ id: "a4" }],
        options: [{ id: "a4" }],
        fuji: { decision_status: "modify" },
        gate: { decision_status: "modify", risk: 0.65 },
        evidence: [{ source: "doc", snippet: "s", confidence: 0.9 }],
        critique: [{ issue: "x" }],
        debate: [{ stance: "pro" }],
        telos_score: 0.7,
        values: { utility: 0.7 },
        plan: [
          { title: "Mask PII", objective: "Remove personal identifiers" },
        ],
        planner: null,
        persona: {},
        memory_citations: [],
        memory_used_count: 0,
        trust_log: null,
        extras: {},
      }),
    } as Response);

    render(<DecisionConsolePage />);
    fireEvent.change(screen.getByPlaceholderText("メッセージを入力"), {
      target: { value: "step expansion" },
    });

    fireEvent.click(screen.getByRole("button", { name: "送信" }));

    await waitFor(() => {
      expect(screen.getByText("FUJI Gate Status")).toBeInTheDocument();
      expect(screen.getByText("MODIFY")).toBeInTheDocument();
      expect(screen.getByText("Step Expansion")).toBeInTheDocument();
      expect(screen.getByText("Mask PII · Planner generated step", { exact: false })).toBeInTheDocument();
    });
  });

});
