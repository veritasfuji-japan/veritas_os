import { expect, test } from "@playwright/test";

const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: "main" });
    await page.goto("/?e2e_governance_scenario=main");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    const governanceTimeline = page.getByRole("region", { name: "governance layer timeline" });
    await expect(governanceTimeline.getByText("participation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("decision_shaping")).toBeVisible();
    await expect(governanceTimeline.getByText("preservation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("degrading")).toBeVisible();
    await expect(governanceTimeline.getByText("intervention_viability:")).toBeVisible();
    await expect(governanceTimeline.getByText("minimal")).toBeVisible();
    await expect(governanceTimeline.getByText("bind_outcome:")).toBeVisible();
    await expect(governanceTimeline.getByText("ESCALATED")).toBeVisible();
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: "fallback" });
    await page.goto("/?e2e_governance_scenario=fallback");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    const governanceTimeline = page.getByRole("region", { name: "governance layer timeline" });
    await expect(governanceTimeline.getByText("participation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("participatory")).toBeVisible();
    await expect(governanceTimeline.getByText("preservation_state:")).toBeVisible();
    await expect(governanceTimeline.getByText("open")).toBeVisible();
    await expect(governanceTimeline.getByText("intervention_viability:")).toBeVisible();
    await expect(governanceTimeline.getByText("high")).toBeVisible();
    await expect(governanceTimeline.getByText("bind_outcome:")).toBeVisible();
    await expect(governanceTimeline.getByText("BLOCKED")).toBeVisible();
  });
});
