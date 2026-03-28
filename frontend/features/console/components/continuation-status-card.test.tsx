import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ContinuationStatusCard } from "./continuation-status-card";

/**
 * Minimal rendering tests for ContinuationStatusCard (phase-1).
 *
 * Verifies:
 *   - Returns null when no continuation data
 *   - Renders claim status when data present
 *   - Renders divergence banner when diverged
 *   - Does not render divergence banner when not diverged
 *   - Shows law version
 *   - Shows revalidation status / outcome
 *   - Shows should-refuse indicator
 */

function makeResult(overrides: Record<string, unknown> = {}) {
  return {
    continuation: {
      state: {
        claim_lineage_id: "lin-1",
        snapshot_id: "s-1",
        claim_status: "live",
        law_version: "v0.1.0-shadow",
        support_basis: { authority: "chain:x", policy: "default" },
        burden_state: { threshold: 1.0, current_level: 1.0 },
        headroom_state: { remaining: 1.0 },
        scope: { allowed_action_classes: ["query"] },
        ...(overrides.state as Record<string, unknown> ?? {}),
      },
      receipt: {
        receipt_id: "r-1",
        revalidation_status: "renewed",
        revalidation_outcome: "renewed",
        should_refuse_before_effect: false,
        divergence_flag: false,
        reason_codes: [],
        ...(overrides.receipt as Record<string, unknown> ?? {}),
      },
    },
  } as never;
}

describe("ContinuationStatusCard", () => {
  it("returns null when result has no continuation data", () => {
    const { container } = render(
      <ContinuationStatusCard result={{} as never} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("returns null when continuation.state is missing", () => {
    const { container } = render(
      <ContinuationStatusCard
        result={{ continuation: { receipt: {} } } as never}
      />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("renders claim status when data is present", () => {
    render(<ContinuationStatusCard result={makeResult()} />);
    expect(screen.getByText("LIVE")).toBeInTheDocument();
  });

  it("renders law version", () => {
    render(<ContinuationStatusCard result={makeResult()} />);
    expect(screen.getByText("v0.1.0-shadow")).toBeInTheDocument();
  });

  it("renders revalidation status and outcome", () => {
    render(<ContinuationStatusCard result={makeResult()} />);
    // Both revalidation_status and revalidation_outcome render "renewed"
    const renewedElements = screen.getAllByText("renewed");
    expect(renewedElements.length).toBeGreaterThanOrEqual(1);
  });

  it("does not show divergence banner when not diverged", () => {
    render(<ContinuationStatusCard result={makeResult()} />);
    // Japanese default: "弱化" is part of the divergence banner text
    expect(screen.queryByText(/弱化/)).not.toBeInTheDocument();
  });

  it("shows divergence banner when diverged", () => {
    render(
      <ContinuationStatusCard
        result={makeResult({
          state: { claim_status: "degraded" },
          receipt: {
            revalidation_status: "degraded",
            revalidation_outcome: "degraded",
            divergence_flag: true,
          },
        })}
      />,
    );
    // Default locale is "ja" — t() returns first (Japanese) argument
    expect(screen.getByText(/弱化/)).toBeInTheDocument();
    expect(screen.getByText("DEGRADED")).toBeInTheDocument();
  });

  it("shows should-refuse YES when set", () => {
    render(
      <ContinuationStatusCard
        result={makeResult({
          state: { claim_status: "revoked" },
          receipt: {
            revalidation_status: "revoked",
            revalidation_outcome: "revoked",
            divergence_flag: true,
            should_refuse_before_effect: true,
          },
        })}
      />,
    );
    expect(screen.getByText("YES")).toBeInTheDocument();
  });

  it("shows reason codes when present", () => {
    render(
      <ContinuationStatusCard
        result={makeResult({
          state: { claim_status: "narrowed" },
          receipt: {
            revalidation_status: "narrowed",
            divergence_flag: true,
            reason_codes: ["ACTION_CLASS_NOT_ALLOWED"],
          },
        })}
      />,
    );
    expect(
      screen.getByText("ACTION_CLASS_NOT_ALLOWED"),
    ).toBeInTheDocument();
  });
});
