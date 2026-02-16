import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const TEST_KEY = process.env.VERITAS_API_KEY ?? "test-e2e-key";

test("console → audit → governance update flow", async ({ page }) => {
  await page.goto("/console");
  await expect(page.getByText("Decision Console")).toBeVisible();

  await page.getByLabel("X-API-Key").fill(TEST_KEY);
  const preset = page
    .locator("div", { hasText: "危険プリセット（安全拒否確認用）" })
    .getByRole("button")
    .first();
  await expect(preset).toBeVisible();
  await preset.click();

  await expect(page.getByText("fuji/gate")).toBeVisible();

  const requestText = await page
    .locator('section[aria-label="trust_log"] pre')
    .innerText()
    .catch(() => "");
  const requestIdMatch = requestText.match(/"request_id"\s*:\s*"([^"]+)"/);
  const requestId = requestIdMatch?.[1];

  await page.goto("/audit");
  await page.getByLabel("X-API-Key").fill(TEST_KEY);

  if (requestId) {
    await page.getByPlaceholder("request_id").fill(requestId);
    await page.getByRole("button", { name: "検索" }).click();
    await expect(page.getByText(/count:/)).toBeVisible();
  } else {
    await page.getByRole("button", { name: "最新ログを読み込み" }).click();
    await expect(page.getByText(/表示件数:/)).toBeVisible();
  }

  await page.goto("/governance");
  await page.getByLabel("X-API-Key").fill(TEST_KEY);
  await page.getByRole("button", { name: "現在のpolicyを読み込み" }).click();
  await expect(page.getByText("policy を読み込みました。")).toBeVisible();

  await page.getByLabel("FUJI rule enabled").click();
  await page.getByLabel("リスク閾値").fill("0.45");
  await page.getByLabel("自動停止条件").fill("risk_threshold_exceeded,manual_override");
  await page.getByLabel("ログ保持期間").fill("120");
  await page.getByLabel("監査強度").selectOption("high");
  await page.getByRole("button", { name: "policy更新" }).click();

  await expect(page.getByText("policy を更新しました。")).toBeVisible();
  await expect(page.getByText(/risk_threshold:/)).toBeVisible();
});

test("@a11y major pages have no serious/critical a11y violations", async ({ page }) => {
  for (const route of ["/", "/console", "/audit", "/governance"]) {
    await page.goto(route);
    await page.waitForLoadState("networkidle");
    const accessibilityScanResults = await new AxeBuilder({ page }).analyze();
    const blockingViolations = accessibilityScanResults.violations.filter(
      (violation) => violation.impact === "critical" || violation.impact === "serious",
    );
    expect(blockingViolations).toEqual([]);
  }
});
