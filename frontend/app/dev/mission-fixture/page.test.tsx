import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import DevMissionFixturePage, { isDevMissionFixtureEnabled } from "./page";

describe("DevMissionFixturePage", () => {
  it("renders a dev-only static mission fixture with governance observation fields", async () => {
    render(await DevMissionFixturePage({ nodeEnv: "test" }));

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

  it("disables the fixture viewer in production", async () => {
    render(await DevMissionFixturePage({ nodeEnv: "production" }));

    expect(screen.getByTestId("dev-mission-fixture-disabled")).toBeInTheDocument();
    expect(screen.getByText("DEV-ONLY FIXTURE DISABLED")).toBeInTheDocument();
    expect(screen.getByText("This route is disabled in production.")).toBeInTheDocument();
    expect(screen.queryByText("Governance observation")).not.toBeInTheDocument();
  });
});

describe("isDevMissionFixtureEnabled", () => {
  it("returns true for development and test, false for production", () => {
    expect(isDevMissionFixtureEnabled("development")).toBe(true);
    expect(isDevMissionFixtureEnabled("test")).toBe(true);
    expect(isDevMissionFixtureEnabled("production")).toBe(false);
  });
});
