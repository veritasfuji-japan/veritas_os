import { test, expect } from "@playwright/test";

const GOVERNANCE_ENDPOINT = "**/api/veritas/v1/report/governance";

test.describe("Mission Control: governance feed frontend E2E", () => {
  test("main path reaches UI from /api/veritas/v1/report/governance", async ({ page }) => {
    await page.route(GOVERNANCE_ENDPOINT, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          governance_layer_snapshot: {
            participation_state: "decision_shaping",
            preservation_state: "degrading",
            intervention_viability: "minimal",
            bind_outcome: "ESCALATED",
          },
        }),
      });
    });

    await page.goto("/");
    await page.waitForResponse((response) => response.url().includes("/api/veritas/v1/report/governance"));
    const timeline = page.getByRole("region", { name: "governance layer timeline" });

    await expect(
      page.getByRole("heading", { name: /(コマンドダッシュボード|Command Dashboard)/ }),
    ).toBeVisible();
    await expect(timeline).toBeVisible();
    await expect(timeline.getByText(/^participation_state:/)).toBeVisible();
    await expect(timeline.getByText(/^decision_shaping$/)).toBeVisible();
    await expect(timeline.getByText(/^preservation_state:/)).toBeVisible();
    await expect(timeline.getByText(/^degrading$/)).toBeVisible();
    await expect(timeline.getByText(/intervention_viability:/)).toBeVisible();
    await expect(timeline.getByText(/^minimal$/)).toBeVisible();
    await expect(timeline.getByText(/^bind_outcome:/)).toBeVisible();
    await expect(timeline.getByText(/^ESCALATED$/)).toBeVisible();

    await expect(page.getByText("BLOCKED", { exact: true })).toHaveCount(0);
  });

  test("endpoint unavailable path renders fallback safety snapshot without breaking page", async ({ page }) => {
    await page.route(GOVERNANCE_ENDPOINT, async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "service_unavailable" }),
      });
    });

    await page.goto("/");
    await page.waitForResponse((response) => response.url().includes("/api/veritas/v1/report/governance"));
    const timeline = page.getByRole("region", { name: "governance layer timeline" });

    await expect(
      page.getByRole("heading", { name: /(コマンドダッシュボード|Command Dashboard)/ }),
    ).toBeVisible();
    await expect(timeline).toBeVisible();
    await expect(timeline.getByText(/^participation_state:/)).toBeVisible();
    await expect(timeline.getByText(/^participatory$/)).toBeVisible();
    await expect(timeline.getByText(/^preservation_state:/)).toBeVisible();
    await expect(timeline.getByText(/^open$/)).toBeVisible();
    await expect(timeline.getByText(/intervention_viability:/)).toBeVisible();
    await expect(timeline.getByText(/^high$/)).toBeVisible();
    await expect(timeline.getByText(/^bind_outcome:/)).toBeVisible();
    await expect(timeline.getByText(/^BLOCKED$/)).toBeVisible();

    await expect(page.getByText("decision_shaping", { exact: true })).toHaveCount(0);
    await expect(page.getByText("ESCALATED", { exact: true })).toHaveCount(0);
  });
});
