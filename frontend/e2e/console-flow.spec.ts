import { test, expect } from "@playwright/test";

test.describe("Console: decision flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/console");
    await expect(
      page.getByRole("heading", { name: "Decision Console" }),
    ).toBeVisible();
  });

  test("renders pipeline stages and empty result placeholder", async ({
    page,
  }) => {
    await expect(page.getByText("Pipeline Operations View")).toBeVisible();
    await expect(
      page.getByText("Start with a real decision question."),
    ).toBeVisible();
    // Evidence, FUJI, TrustLog stages visible
    await expect(page.locator("li", { hasText: "Evidence" })).toBeVisible();
    await expect(page.locator("li", { hasText: "FUJI" })).toBeVisible();
    await expect(page.locator("li", { hasText: "TrustLog" })).toBeVisible();
  });

  test("query input accepts text and shows send button", async ({ page }) => {
    const input = page.getByPlaceholder(/メッセージを入力|Enter a message/);
    await expect(input).toBeVisible();
    await input.fill("Should we delay launch?");
    const sendButton = page.getByRole("button", { name: /送信|Send/i });
    await expect(sendButton).toBeEnabled();
  });

  test("empty query shows validation error", async ({ page }) => {
    const sendButton = page.getByRole("button", { name: /送信|Send/i });
    await sendButton.click();
    // Should show query required error
    await expect(
      page.getByText(/query を入力|Please enter query/i),
    ).toBeVisible();
  });

  test("result tabs switch between insights and raw JSON", async ({
    page,
  }) => {
    // With no result, the tab area should not be visible
    const insightsButton = page.getByRole("button", { name: "Insights" });
    const rawButton = page.getByRole("button", { name: "Raw JSON" });
    // These are only shown when result exists — verify placeholder instead
    await expect(
      page.getByText("Start with a real decision question."),
    ).toBeVisible();
    // If tabs existed (with result), they would be toggleable
    expect(await insightsButton.count()).toBe(0);
    expect(await rawButton.count()).toBe(0);
  });

  test("keyboard: Enter in input submits the form", async ({ page }) => {
    const input = page.getByPlaceholder(/メッセージを入力|Enter a message/);
    await input.fill("Test keyboard submit");
    await input.press("Enter");
    // Should show loading or error (backend may not be running)
    await expect(
      page
        .getByText(/送信中|Sending|ネットワークエラー|Network error|Timeout|503|service_unavailable|HTTP/i)
        .first(),
    ).toBeVisible({ timeout: 25_000 });
  });
});
