import { expect, test } from "@playwright/test";

const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: "main" });
    await page.goto("/?e2e_governance_scenario=main");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expect(page.getByText("participation_state:")).toBeVisible();
    await expect(page.getByText("decision_shaping", { exact: false })).toBeVisible();
    await expect(page.getByText("preservation_state:")).toBeVisible();
    await expect(page.getByText("degrading", { exact: false })).toBeVisible();
    await expect(page.getByText("intervention_viability:")).toBeVisible();
    await expect(page.getByText("minimal", { exact: false })).toBeVisible();
    await expect(page.getByText("bind_outcome:")).toBeVisible();
    await expect(page.getByText("ESCALATED", { exact: false })).toBeVisible();
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.setExtraHTTPHeaders({ [E2E_SCENARIO_HEADER]: "fallback" });
    await page.goto("/?e2e_governance_scenario=fallback");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expect(page.getByText("participation_state:")).toBeVisible();
    await expect(page.getByText("participatory", { exact: false })).toBeVisible();
    await expect(page.getByText("preservation_state:")).toBeVisible();
    await expect(page.getByText("open", { exact: false })).toBeVisible();
    await expect(page.getByText("intervention_viability:")).toBeVisible();
    await expect(page.getByText("high", { exact: false })).toBeVisible();
    await expect(page.getByText("bind_outcome:")).toBeVisible();
    await expect(page.getByText("BLOCKED", { exact: false })).toBeVisible();
  });
});
