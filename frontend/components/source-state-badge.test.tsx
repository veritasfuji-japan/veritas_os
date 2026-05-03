import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SourceStateBadge } from "./source-state-badge";

describe("SourceStateBadge", () => {
  it("renders state", () => {
    render(<SourceStateBadge state="fixture" />);
    expect(screen.getByText("fixture")).toBeInTheDocument();
  });

  it("includes reason in accessibility text", () => {
    render(<SourceStateBadge state="demo" reason="demo_scenario" />);
    expect(screen.getByLabelText("source state: demo (demo_scenario)")).toBeInTheDocument();
  });
});
