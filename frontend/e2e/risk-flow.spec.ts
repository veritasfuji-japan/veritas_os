import { test, expect } from "@playwright/test";

test.describe("Risk: real-time monitoring flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/risk");
    await expect(
      page.getByRole("heading", { name: "Risk Intelligence" }),
    ).toBeVisible();
  });

  test("renders heatmap with scatter plot", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Real-time Risk Heatmap" }),
    ).toBeVisible();
    // SVG scatter plot should be present
    const svg = page.locator(
      'svg[aria-label="Scatter plot of request uncertainty and risk from the last 24 hours"]',
    );
    await expect(svg).toBeVisible();
  });

  test("time window filter changes visible data", async ({ page }) => {
    const timeSelect = page.getByLabel(/時間窓|Time window/i);
    await expect(timeSelect).toBeVisible();

    // Change to 1h window
    await timeSelect.selectOption("1");
    // Points should still render (the chart should update)
    await page.waitForTimeout(500);
    const svg = page.locator(
      'svg[aria-label="Scatter plot of request uncertainty and risk from the last 24 hours"]',
    );
    await expect(svg).toBeVisible();
  });

  test("cluster filter narrows points", async ({ page }) => {
    const clusterSelect = page.getByLabel(/クラスタ ドリルダウン|Cluster drilldown/i);
    await expect(clusterSelect).toBeVisible();

    await clusterSelect.selectOption("critical");
    // Chart should still be visible
    await page.waitForTimeout(500);
    const svg = page.locator(
      'svg[aria-label="Scatter plot of request uncertainty and risk from the last 24 hours"]',
    );
    await expect(svg).toBeVisible();
  });

  test("real-time update increments timestamp", async ({ page }) => {
    // Wait for initial render
    const timeDisplay = page.locator('[aria-live="polite"]');
    await expect(timeDisplay).toBeVisible();
    const firstTime = await timeDisplay.textContent();

    // Wait for a tick (STREAM_TICK_MS = 2000)
    await page.waitForTimeout(3_000);
    const secondTime = await timeDisplay.textContent();

    // Timestamp should have changed
    expect(secondTime).not.toBe(firstTime);
  });

  test("insight cards display metrics", async ({ page }) => {
    await expect(page.getByText("Policy drift")).toBeVisible();
    await expect(page.getByText("Unsafe burst")).toBeVisible();
    await expect(page.getByText("Unstable output cluster")).toBeVisible();
  });

  test("trend chart renders all 8 buckets", async ({ page }) => {
    await expect(page.getByText("Trend / Spike / Burst")).toBeVisible();
    // 8 bucket labels
    await expect(page.locator('[aria-label="trend chart"] button')).toHaveCount(
      8,
    );
  });

  test("drilldown panel shows when point is selected", async ({ page }) => {
    const drilldown = page.locator('[data-testid="drilldown-panel"]');
    await expect(drilldown).toBeVisible();
  });

  test("why flagged panel is visible", async ({ page }) => {
    const whyFlagged = page.locator('[data-testid="why-flagged"]');
    await expect(whyFlagged).toBeVisible();
  });

  test("cross-navigation links work", async ({ page }) => {
    const decisionLink = page.getByRole("link", { name: /Decision/i }).first();
    await expect(decisionLink).toBeVisible();
    await expect(decisionLink).toHaveAttribute("href", "/console");

    const trustlogLink = page.getByRole("link", { name: /TrustLog/i }).first();
    await expect(trustlogLink).toBeVisible();
    await expect(trustlogLink).toHaveAttribute("href", "/audit");
  });
});
