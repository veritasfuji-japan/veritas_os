import { expect, test } from "@playwright/test";

test("browser session lookup receives the issued scoped Cookie", async ({ page, context }) => {
  await page.goto("/governance");
  const cookies = (await context.cookies()).filter((cookie) => cookie.name === "__veritas_bff");
  expect(cookies).toHaveLength(1);
  expect(cookies[0]).toMatchObject({ path: "/api/veritas", httpOnly: true, sameSite: "Strict" });
  const result = await page.evaluate(async () => {
    const response = await fetch("/api/veritas/session");
    return { status: response.status, body: await response.json() };
  });
  expect(result).toEqual({ status: 200, body: { ok: true, role: "admin" } });
  await expect(page.locator("text=Authenticated role:").first()).toContainText("admin");
  await expect(page.getByRole("button", { name: /ポリシーを読み込む|Load policy/i })).toBeEnabled();
  expect((await context.cookies("http://127.0.0.1:3101/api/auth/session"))
    .filter((cookie) => cookie.name === "__veritas_bff")).toHaveLength(0);
});

test("legacy lookup stays outside the Cookie scope", async ({ page }) => {
  await page.goto("/governance");
  const status = await page.evaluate(async () => (await fetch("/api/auth/session")).status);
  expect(status).toBe(401);
});

test("new lookup rejects malformed Authorization despite an admin Cookie", async ({ page }) => {
  await page.goto("/governance");
  const result = await page.evaluate(async () => {
    const response = await fetch("/api/veritas/session", { headers: { Authorization: "Bearer" } });
    return { status: response.status, body: await response.json() };
  });
  expect(result).toEqual({ status: 401, body: { ok: false, error: "unauthorized" } });
});

test("new lookup honors explicit viewer Bearer over admin Cookie", async ({ page }) => {
  await page.goto("/governance");
  const result = await page.evaluate(async () => {
    const response = await fetch("/api/veritas/session", {
      headers: { Authorization: "Bearer  cookie-path-viewer-test-only" },
    });
    return { status: response.status, body: await response.json() };
  });
  expect(result).toEqual({ status: 200, body: { ok: true, role: "viewer" } });
});
