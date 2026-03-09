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
});
