import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("GET /api/auth/session", () => {
  it("returns authenticated admin role", async () => {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"admin-token":"admin"}');
    const request = new NextRequest("http://localhost/api/auth/session", {
      headers: { authorization: "Bearer admin-token" },
    });

    const response = await GET(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true, role: "admin" });
  });

  it("returns authenticated operator role", async () => {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"operator-token":"operator"}');
    const request = new NextRequest("http://localhost/api/auth/session", {
      headers: { authorization: "Bearer operator-token" },
    });

    const response = await GET(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true, role: "operator" });
  });

  it("returns authenticated viewer role from cookie", async () => {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"viewer-token":"viewer"}');
    const request = new NextRequest("http://localhost/api/auth/session", {
      headers: { cookie: "__veritas_bff=viewer-token" },
    });

    const response = await GET(request);

    expect(response.status).toBe(200);
    await expect(response.json()).resolves.toEqual({ ok: true, role: "viewer" });
  });

  it("returns 401 when unauthenticated", async () => {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"admin-token":"admin"}');
    const response = await GET(new NextRequest("http://localhost/api/auth/session"));

    expect(response.status).toBe(401);
    await expect(response.json()).resolves.toEqual({ ok: false, error: "unauthorized" });
  });

  it("returns 503 when token map is missing", async () => {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", "");
    const response = await GET(new NextRequest("http://localhost/api/auth/session"));

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toEqual({ ok: false, error: "server_misconfigured" });
  });

  it("does not expose sensitive token or cookie values", async () => {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"admin-token":"admin"}');
    const response = await GET(new NextRequest("http://localhost/api/auth/session", {
      headers: { authorization: "Bearer admin-token", cookie: "__veritas_bff=admin-token" },
    }));

    const payload = await response.json() as Record<string, unknown>;
    expect(payload).not.toHaveProperty("token");
    expect(payload).not.toHaveProperty("apiKey");
    expect(payload).not.toHaveProperty("cookie");
  });
});
