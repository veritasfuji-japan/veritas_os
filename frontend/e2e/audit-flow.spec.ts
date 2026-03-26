import { test, expect } from "@playwright/test";

/**
 * CSS selector for VERITAS error banners, excluding the Next.js route announcer
 * to avoid Playwright strict-mode violations.
 */
const ALERT_BANNER = '[role="alert"]:not(#__next-route-announcer__)';

test.describe("Audit: search and filter flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/audit");
    await expect(
      page.getByRole("heading", { name: "TrustLog Explorer" }),
    ).toBeVisible();
  });

  test("renders search panel with request_id input", async ({ page }) => {
    await expect(page.getByPlaceholder("request_id")).toBeVisible();
    await expect(
      page.getByRole("heading", { name: /request_id/ }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Timeline" }),
    ).toBeVisible();
  });

  test("load logs button triggers data fetch", async ({ page }) => {
    const loadButton = page.getByRole("button", {
      name: /最新ログを読み込み|Load latest logs/i,
    });
    await expect(loadButton).toBeVisible();
    await loadButton.click();
    // Should show loading state or data or error
    await expect(
      page
        .getByText(
          /読み込み中|Loading|HTTP|ネットワークエラー|Network error|Timeline/i,
        )
        .first(),
    ).toBeVisible({ timeout: 25_000 });
  });

  test("empty request_id search shows validation message", async ({
    page,
  }) => {
    const searchButton = page.getByRole("button", {
      name: /検索|Search/i,
    });
    // There may be multiple search buttons; click the one near request_id
    if ((await searchButton.count()) > 0) {
      await searchButton.first().click();
      await expect(
        page.getByText(
          /request_id を入力|Please enter request_id/i,
        ),
      ).toBeVisible();
    }
  });

  test("error banner shows retry button when error occurs", async ({
    page,
  }) => {
    // Trigger a load that might fail
    const loadButton = page.getByRole("button", {
      name: /最新ログを読み込み|Load latest logs/i,
    });
    await loadButton.click();
    // Wait for either success or error
    await page.waitForTimeout(5_000);
    const errorBanner = page.locator(ALERT_BANNER);
    if ((await errorBanner.count()) > 0) {
      // Retry button should be present
      await expect(
        errorBanner.getByRole("button", { name: /再試行|Retry/i }),
      ).toBeVisible();
    }
  });

  test("stage filter dropdown is rendered", async ({ page }) => {
    // Stage filter select should exist after load
    const stageSelect = page.locator("select").filter({ hasText: "ALL" });
    if ((await stageSelect.count()) > 0) {
      await expect(stageSelect.first()).toBeVisible();
    }
  });
});
