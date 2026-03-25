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
            decision_status: "deny",
            risk_score: 0.85,
            reasons: ["PII detected"],
            violations: [
              { rule: "PII_RULE", detail: "Email found", severity: "high" },
            ],
          },
          gate: { decision_status: "deny", risk: 0.85 },
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
});
