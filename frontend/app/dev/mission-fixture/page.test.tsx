import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DevMissionFixturePage from "./page";

describe("DevMissionFixturePage", () => {
  it("renders a dev-only static mission fixture with governance observation fields", () => {
    render(<DevMissionFixturePage />);

    expect(screen.getAllByText("DEV-ONLY FIXTURE").length).toBeGreaterThan(0);
    expect(screen.getByText("Runtime behavior is unchanged")).toBeInTheDocument();
    expect(screen.getByText("Production still fails closed")).toBeInTheDocument();
    expect(screen.getByText("Observe Mode runtime is not enabled")).toBeInTheDocument();

    expect(screen.getByText("Governance observation")).toBeInTheDocument();
    expect(screen.getByText("observe")).toBeInTheDocument();
    expect(screen.getByText("development")).toBeInTheDocument();
    expect(screen.getByText("would_have_blocked")).toBeInTheDocument();
    expect(screen.getAllByText("true").length).toBeGreaterThan(0);
    expect(screen.getByText("policy_violation:missing_authority_evidence")).toBeInTheDocument();
    expect(screen.getByText("effective_outcome")).toBeInTheDocument();
    expect(screen.getByText("proceed")).toBeInTheDocument();
    expect(screen.getByText("observed_outcome")).toBeInTheDocument();
    expect(screen.getByText("block")).toBeInTheDocument();
  });
});
