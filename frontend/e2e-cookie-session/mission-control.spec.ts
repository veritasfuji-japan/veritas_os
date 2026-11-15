import { createServer } from "node:http";

import { expect, test } from "@playwright/test";

const backend = createServer((request, response) => {
  if (request.method !== "GET" || request.url !== "/v1/governance/live-snapshot") {
    response.writeHead(404).end();
    return;
  }
  if (request.headers["x-api-key"] !== "cookie-path-backend-test-only" ||
      request.headers["x-role"] !== "admin") {
    response.writeHead(403).end();
    return;
  }
  response.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({
    governance_layer_snapshot: {
      participation_state: "decision_shaping",
      preservation_state: "degrading",
      bind_outcome: "ESCALATED",
    },
  }));
});

test.beforeAll(async () => {
  await new Promise<void>((resolve, reject) => {
    backend.once("error", reject);
    backend.listen(3102, "127.0.0.1", resolve);
  });
});

test.afterAll(async () => {
  if (backend.listening) {
    await new Promise<void>((resolve, reject) => {
      backend.close((error) => error ? reject(error) : resolve());
    });
  }
});

test("Mission Control displays live data using the scoped browser session", async ({ page }) => {
  await page.goto("/governance");
  const feedResponse = page.waitForResponse((response) =>
    new URL(response.url()).pathname === "/api/veritas/v1/report/governance",
  );
  const document = await page.goto("/");
  expect(await document?.request().headerValue("cookie")).toBeNull();

  const feed = await feedResponse;
  expect(feed.status()).toBe(200);
  expect(await feed.request().headerValue("cookie")).toContain("__veritas_bff=");
  await expect(page.getByText("decision_shaping", { exact: true }).first()).toBeVisible();
});
