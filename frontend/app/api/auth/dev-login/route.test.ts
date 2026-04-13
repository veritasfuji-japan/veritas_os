import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

function makeRequest(url = "http://localhost:3000/api/auth/dev-login"): Request {
  return new Request(url, { method: "GET" });
}

describe("GET /api/auth/dev-login", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("returns 403 when VERITAS_ENV is production", async () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "some-token");

    const response = await GET(makeRequest());

    expect(response.status).toBe(403);
    const body = await response.json();
    expect(body.error).toBe("forbidden");
  });

  it("returns 403 when NODE_ENV is production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "some-token");

    const response = await GET(makeRequest());

    expect(response.status).toBe(403);
  });

  it("returns 503 when VERITAS_BFF_SESSION_TOKEN is not set", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "");

    const response = await GET(makeRequest());

    expect(response.status).toBe(503);
    const body = await response.json();
    expect(body.error).toBe("not_configured");
  });

  it("sets cookie and redirects to /console by default", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "dev-token");

    const response = await GET(makeRequest());

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/console");

    const setCookie = response.headers.get("set-cookie") ?? "";
    expect(setCookie).toContain("__veritas_bff=dev-token");
    expect(setCookie).toContain("HttpOnly");
    expect(setCookie).toContain("Path=/api/veritas");
    expect(setCookie).toContain("SameSite=lax");
  });

  it("redirects to custom ?redirect= path", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "dev-token");

    const response = await GET(
      makeRequest("http://localhost:3000/api/auth/dev-login?redirect=/audit"),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/audit");
  });

  it("rejects open-redirect attempts by falling back to /console", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "dev-token");

    const response = await GET(
      makeRequest("http://localhost:3000/api/auth/dev-login?redirect=https://evil.example"),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/console");
  });

  it("rejects protocol-relative redirect attempts", async () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "dev-token");

    const response = await GET(
      makeRequest("http://localhost:3000/api/auth/dev-login?redirect=//evil.example.com"),
    );

    expect(response.status).toBe(307);
    expect(response.headers.get("location")).toBe("http://localhost:3000/console");
  });
});
