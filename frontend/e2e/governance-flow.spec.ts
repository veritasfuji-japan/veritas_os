import { test, expect } from "@playwright/test";

test.describe("Governance: policy management flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/governance");
    await expect(
      page.getByRole("heading", { name: "Governance Control" }),
    ).toBeVisible();
  });

  test("renders role selector and mode selector", async ({ page }) => {
    const roleSelect = page.getByLabel("role", { exact: true });
    await expect(roleSelect).toBeVisible();
    await expect(roleSelect).toHaveValue("admin");

    const modeSelect = page.getByLabel("mode", { exact: true });
    await expect(modeSelect).toBeVisible();
    await expect(modeSelect).toHaveValue("standard");
  });

  test("load policy button is visible and clickable", async ({ page }) => {
    const loadButton = page.getByRole("button", {
      name: /ポリシーを読み込む|Load policy/i,
    });
    await expect(loadButton).toBeVisible();
    await expect(loadButton).toBeEnabled();
  });

  test("empty state shown when no policy loaded", async ({ page }) => {
    await expect(
      page.getByText(/ポリシー未読み込み|No policy loaded/i),
    ).toBeVisible();
  });

  test("loading policy shows loading state or error with retry", async ({
    page,
  }) => {
    const loadButton = page.getByRole("button", {
      name: /ポリシーを読み込む|Load policy/i,
    });
    await loadButton.click();

    // Wait for loading or result
    await expect(
      page
        .getByText(
          /読み込み中|Loading|HTTP|ネットワークエラー|Network error|version/i,
        )
        .first(),
    ).toBeVisible({ timeout: 25_000 });

    // If error, verify retry button is present
    const errorBanner = page.locator('[role="alert"]');
    if ((await errorBanner.count()) > 0) {
      await expect(
        errorBanner.getByRole("button", { name: /再試行|Retry/i }),
      ).toBeVisible();
    }
  });

  test("role change updates capability matrix", async ({ page }) => {
    const roleSelect = page.getByLabel("role", { exact: true });

    await roleSelect.selectOption("viewer");
    await expect(page.getByText("Viewer（閲覧専用）")).toBeVisible();

    await roleSelect.selectOption("operator");
    await expect(page.getByText("Operator（運用）")).toBeVisible();
  });

  test("mode change updates explanation panel", async ({ page }) => {
    const modeSelect = page.getByLabel("mode", { exact: true });
    await modeSelect.selectOption("eu_ai_act");
    // Mode explanation summary appears after selecting eu_ai_act
    await expect(page.getByText("EU AI Act 準拠モード")).toBeVisible();
  });

  test("risk gauge displays percentage", async ({ page }) => {
    await expect(page.getByText(/Risk gauge:.*%/)).toBeVisible();
  });

  test("viewer role keeps apply action blocked", async ({ page }) => {
    const loadButton = page.getByRole("button", {
      name: /ポリシーを読み込む|Load policy/i,
    });
    await loadButton.click();
    await expect(
      page
        .getByText(/読み込み中|Loading|HTTP|ネットワークエラー|Network error|version/i)
        .first(),
    ).toBeVisible({ timeout: 25_000 });

    const applyButton = page.getByRole("button", { name: /適用|Apply/i });
    if ((await applyButton.count()) > 0) {
      await page.getByLabel("role", { exact: true }).selectOption("viewer");
      await expect(applyButton).toBeDisabled();
      await expect(page.getByText(/RBAC: apply\/rollback/)).toBeVisible();
      return;
    }

    // Backend unavailable path: keep this test meaningful by validating
    // degraded/error state and retry affordance.
    const errorBanner = page.locator('[role="alert"]');
    await expect(errorBanner).toBeVisible();
    await expect(errorBanner.getByRole("button", { name: /再試行|Retry/i })).toBeVisible();
  });
});
