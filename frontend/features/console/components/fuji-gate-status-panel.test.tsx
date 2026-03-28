import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FujiGateStatusPanel } from "./fuji-gate-status-panel";

describe("FujiGateStatusPanel", () => {
  it("renders placeholder when result is null", () => {
    render(<FujiGateStatusPanel result={null} />);
    expect(screen.getByText(/Run a decision/i)).toBeInTheDocument();
  });

  it("renders basic gate fields", () => {
    render(
      <FujiGateStatusPanel
        result={{
          fuji: { decision_status: "allow" },
          gate: { decision_status: "allow", risk: 0.2 },
        } as never}
      />,
    );
    expect(screen.getByText("allow")).toBeInTheDocument();
    expect(screen.getByText("rule hit")).toBeInTheDocument();
  });

  it("shows drilldown when violations are present", () => {
    render(
      <FujiGateStatusPanel
        result={{
          fuji: {
            decision_status: "block",
            risk_score: 0.85,
            reasons: ["PII detected"],
            violations: [
              { rule: "PII_RULE", detail: "Email found", severity: "high" },
            ],
          },
          gate: { decision_status: "block", risk: 0.85 },
        } as never}
      />,
    );
    expect(screen.getByTestId("fuji-drilldown")).toBeInTheDocument();
    expect(screen.getByText(/risk score, reasons & violations \(1\)/i)).toBeInTheDocument();
  });

  it("does not show drilldown when no extra detail exists", () => {
    render(
      <FujiGateStatusPanel
        result={{
          fuji: { decision_status: "allow" },
          gate: { decision_status: "allow" },
        } as never}
      />,
    );
    expect(screen.queryByTestId("fuji-drilldown")).not.toBeInTheDocument();
  });

  it("applies destructive color for 'rejected' decision", () => {
    const { container } = render(
      <FujiGateStatusPanel
        result={{
          fuji: { decision_status: "rejected" },
          gate: { decision_status: "rejected", risk: 0.9 },
        } as never}
      />,
    );
    const statusEl = container.querySelector(".text-destructive");
    expect(statusEl).toBeInTheDocument();
    expect(statusEl?.textContent).toBe("rejected");
  });

  it("applies destructive color for 'block' decision", () => {
    const { container } = render(
      <FujiGateStatusPanel
        result={{
          fuji: { decision_status: "block" },
          gate: { decision_status: "block", risk: 0.95 },
        } as never}
      />,
    );
    const statusEl = container.querySelector(".text-destructive");
    expect(statusEl).toBeInTheDocument();
    expect(statusEl?.textContent).toBe("block");
  });

  it("applies amber color for 'abstain' decision", () => {
    const { container } = render(
      <FujiGateStatusPanel
        result={{
          fuji: { decision_status: "abstain" },
          gate: { decision_status: "abstain" },
        } as never}
      />,
    );
    const statusEl = container.querySelector(".text-amber-400");
    expect(statusEl).toBeInTheDocument();
    expect(statusEl?.textContent).toBe("abstain");
  });
});
