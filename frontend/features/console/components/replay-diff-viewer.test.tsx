import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReplayDiffViewer } from "./replay-diff-viewer";

describe("ReplayDiffViewer", () => {
  it("highlights changed fields", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { id: "a", score: 0.9 },
          extras: { replay_previous_chosen: { id: "a", score: 0.5 } },
        } as never}
      />,
    );

    expect(screen.getByText("score")).toBeInTheDocument();
    expect(screen.getByText("0.5")).toBeInTheDocument();
    expect(screen.getByText("0.9")).toBeInTheDocument();
  });

  it("shows severity column header", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { decision: "allow" },
          extras: { replay_previous_chosen: { decision: "reject" } },
        } as never}
      />,
    );

    expect(screen.getByText("Severity")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
  });

  it("shows divergence badge for critical changes", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { decision: "allow" },
          extras: { replay_previous_chosen: { decision: "reject" } },
        } as never}
      />,
    );

    expect(screen.getByTestId("divergence-badge")).toHaveTextContent("Critical Divergence");
  });

  it("shows acceptable divergence badge when only non-critical fields change", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { evidence: "a" },
          extras: { replay_previous_chosen: { evidence: "b" } },
        } as never}
      />,
    );

    expect(screen.getByTestId("divergence-badge")).toHaveTextContent("Acceptable Divergence");
  });

  it("shows no divergence badge when nothing changed", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { id: "a" },
          extras: { replay_previous_chosen: { id: "a" } },
        } as never}
      />,
    );

    expect(screen.getByTestId("divergence-badge")).toHaveTextContent("No Divergence");
  });

  it("renders nested objects as expandable details instead of [object Object]", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { meta: { foo: "bar" } },
          extras: { replay_previous_chosen: { meta: { foo: "baz" } } },
        } as never}
      />,
    );

    // Should show expandable summary, not "[object Object]"
    expect(screen.getAllByText("{1 keys}").length).toBeGreaterThan(0);
    expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
  });

  it("shows change summary when fields differ", () => {
    render(
      <ReplayDiffViewer
        result={{
          chosen: { id: "a", score: 0.9 },
          extras: { replay_previous_chosen: { id: "a", score: 0.5 } },
        } as never}
      />,
    );

    expect(screen.getByTestId("change-summary")).toHaveTextContent("1 field(s) changed: score");
  });
});
