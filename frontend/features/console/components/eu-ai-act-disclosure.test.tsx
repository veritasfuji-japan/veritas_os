import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EUAIActDisclosure } from "./eu-ai-act-disclosure";
import type { DecideResponse } from "@veritas/types";

function buildResult(overrides: Partial<DecideResponse> = {}): DecideResponse {
  return {
    ok: true,
    error: null,
    request_id: "test-req",
    version: "1.0",
    chosen: {},
    alternatives: [],
    options: [],
    decision_status: "allow",
    rejection_reason: null,
    values: null,
    telos_score: 0.8,
    fuji: {},
    gate: { risk: 0, telos_score: 0.8, decision_status: "allow", modifications: [] },
    evidence: [],
    critique: [],
    debate: [],
    extras: {},
    plan: null,
    planner: null,
    persona: {},
    memory_citations: [],
    memory_used_count: 0,
    trust_log: null,
    ...overrides,
  };
}

describe("EUAIActDisclosure", () => {
  it("renders nothing when no disclosure fields are present", () => {
    const { container } = render(<EUAIActDisclosure result={buildResult()} />);
    expect(container.firstChild).toBeNull();
  });

  it("renders ai_disclosure text", () => {
    render(
      <EUAIActDisclosure
        result={buildResult({ ai_disclosure: "This is AI-generated content." })}
      />,
    );
    expect(screen.getByTestId("ai-disclosure")).toHaveTextContent("This is AI-generated content.");
  });

  it("renders regulation_notice text", () => {
    render(
      <EUAIActDisclosure
        result={buildResult({ regulation_notice: "Subject to EU AI Act." })}
      />,
    );
    expect(screen.getByTestId("regulation-notice")).toHaveTextContent("Subject to EU AI Act.");
  });

  it("renders affected_parties_notice as expandable details", () => {
    render(
      <EUAIActDisclosure
        result={buildResult({
          affected_parties_notice: {
            right_to_explanation: true,
            right_to_contest: true,
          },
        })}
      />,
    );
    expect(screen.getByText("Affected Parties Notice")).toBeInTheDocument();
  });

  it("renders section heading", () => {
    render(
      <EUAIActDisclosure
        result={buildResult({ ai_disclosure: "AI content" })}
      />,
    );
    expect(screen.getByText("EU AI Act Disclosure")).toBeInTheDocument();
  });
});
