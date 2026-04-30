import { expect, test } from "@playwright/test";

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    await page.goto("/?e2e_governance_scenario=main");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expect(page.getByText(/participation_state:\s*decision_shaping/)).toBeVisible();
    await expect(page.getByText(/preservation_state:\s*degrading/)).toBeVisible();
    await expect(page.getByText(/intervention_viability:\s*minimal/)).toBeVisible();
    await expect(page.getByText(/bind_outcome:\s*ESCALATED/)).toBeVisible();
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.goto("/?e2e_governance_scenario=fallback");

    await expect(
      page.getByRole("heading", { name: /コマンドダッシュボード|Command Dashboard/i }),
    ).toBeVisible();

    await expect(page.getByText(/participation_state:\s*participatory/)).toBeVisible();
    await expect(page.getByText(/preservation_state:\s*open/)).toBeVisible();
    await expect(page.getByText(/intervention_viability:\s*high/)).toBeVisible();
    await expect(page.getByText(/bind_outcome:\s*BLOCKED/)).toBeVisible();
  });
});
