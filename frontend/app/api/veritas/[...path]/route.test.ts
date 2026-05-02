import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  authenticateRoleFromHeaders,
  hasUnsafeSegment,
  matchPolicy,
  parseAuthTokensConfig,
} from "./route-auth";
import { getBodySizeBytes } from "./body-size";
import { GET } from "./route";
import { resolveTraceId } from "./trace-id";
import {
  resetApiBaseUrlWarningStateForTest,
  resolveApiBaseUrl,
} from "./route-config";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  resetApiBaseUrlWarningStateForTest();
});

describe("resolveApiBaseUrl", () => {
  it("uses server-only VERITAS_API_BASE_URL when provided", () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "");

    expect(resolveApiBaseUrl()).toBe("http://internal-api:8000");
  });

  it("falls back to localhost when VERITAS_API_BASE_URL is not set", () => {
    vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "http://public-api:8000");
    vi.stubEnv("VERITAS_API_BASE_URL", "");

    expect(resolveApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("returns null in production when VERITAS_API_BASE_URL is missing", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "");

    expect(resolveApiBaseUrl()).toBeNull();
  });

  it("returns null when NODE_ENV is production and VERITAS_API_BASE_URL is missing", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("VERITAS_API_BASE_URL", "");

    expect(resolveApiBaseUrl()).toBeNull();
  });

  it("returns null in production when NEXT_PUBLIC_VERITAS_API_BASE_URL is set", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "http://public-api:8000");

    expect(resolveApiBaseUrl()).toBeNull();
  });

  it("emits security warning once when NEXT_PUBLIC_VERITAS_API_BASE_URL is set", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "http://public-api:8000");
    vi.stubEnv("VERITAS_API_BASE_URL", "");

    resolveApiBaseUrl();
    resolveApiBaseUrl();

    expect(warnSpy).toHaveBeenCalledTimes(1);
    expect(warnSpy.mock.calls[0]?.[0]).toContain("[security-warning]");
  });

  it("emits a blocking warning when NEXT_PUBLIC_VERITAS_API_BASE_URL is set in production", () => {
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "http://public-api:8000");

    resolveApiBaseUrl();

    expect(warnSpy).toHaveBeenCalledTimes(2);
    expect(warnSpy.mock.calls[1]?.[0]).toContain("must be unset in production");
  });

});

describe("veritas bff route auth and authorization", () => {
  it("parses valid token-to-role config", () => {
    const tokenMap = parseAuthTokensConfig(
      '{"token-viewer":"viewer","token-admin":"admin","ignored":"bad-role"}',
    );

    expect(tokenMap.get("token-viewer")).toBe("viewer");
    expect(tokenMap.get("token-admin")).toBe("admin");
    expect(tokenMap.has("ignored")).toBe(false);
  });

  it("rejects unsupported auth config format", () => {
    const tokenMap = parseAuthTokensConfig("[]");

    expect(tokenMap.size).toBe(0);
  });

  it("returns 503 when auth token map is missing", () => {
    const result = authenticateRoleFromHeaders(new Headers(), new Map());

    expect(result.role).toBeUndefined();
    expect(result.errorResponse?.status).toBe(503);
  });

  it("returns 401 when bearer token is not provided", () => {
    const headers = new Headers();
    const result = authenticateRoleFromHeaders(headers, new Map([["token-admin", "admin"]]));

    expect(result.role).toBeUndefined();
    expect(result.errorResponse?.status).toBe(401);
  });

  it("returns role for valid bearer token", () => {
    const headers = new Headers({ authorization: "Bearer token-operator" });
    const result = authenticateRoleFromHeaders(
      headers,
      new Map([
        ["token-viewer", "viewer"],
        ["token-operator", "operator"],
      ]),
    );

    expect(result.role).toBe("operator");
    expect(result.errorResponse).toBeUndefined();
  });

  it("applies route policies for admin-only and operator endpoints", () => {
    const governanceGet = matchPolicy(["v1", "governance", "policy"], "GET");
    const governancePut = matchPolicy(["v1", "governance", "policy"], "PUT");
    const decidePost = matchPolicy(["v1", "decide"], "POST");
    const compliancePut = matchPolicy(["v1", "compliance", "config"], "PUT");
    const complianceGet = matchPolicy(["v1", "compliance", "config"], "GET");

    expect(governancePut?.policy.roles).toEqual(["admin"]);
    expect(governanceGet?.policy.roles).toEqual(["admin"]);
    expect(decidePost?.policy.roles).toEqual(["operator", "admin"]);
    expect(compliancePut?.policy.roles).toEqual(["admin"]);
    expect(complianceGet?.policy.roles).toEqual(["viewer", "operator", "admin"]);
  });

  it("blocks unsafe path segments", () => {
    expect(hasUnsafeSegment(["v1", "..", "policy"])).toBe(true);
    expect(matchPolicy(["v1", "..", "policy"], "GET")).toBeNull();
  });
});

describe("getBodySizeBytes", () => {
  it("returns ASCII length as bytes", () => {
    expect(getBodySizeBytes("abcd")).toBe(4);
  });

  it("counts multibyte UTF-8 characters correctly", () => {
    expect(getBodySizeBytes("あ")).toBe(3);
    expect(getBodySizeBytes("😀")).toBe(4);
  });
});

describe("resolveTraceId", () => {
  it("accepts a valid x-trace-id", () => {
    const headers = new Headers({ "x-trace-id": "trace-abc12345" });

    expect(resolveTraceId(headers)).toBe("trace-abc12345");
  });

  it("falls back to x-request-id", () => {
    const headers = new Headers({ "x-request-id": "request-abc12345" });

    expect(resolveTraceId(headers)).toBe("request-abc12345");
  });

  it("generates a uuid when provided ids are invalid", () => {
    const headers = new Headers({ "x-trace-id": "..\n" });
    const traceId = resolveTraceId(headers);

    expect(traceId).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i,
    );
  });
});


describe("veritas bff route proxy - full request lifecycle", () => {
  it("returns 404 when path does not match any policy", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const request = new NextRequest("http://localhost/api/veritas/v1/unknown/endpoint", {
      headers: { authorization: "Bearer token-admin" },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "unknown", "endpoint"] }),
    });

    expect(response.status).toBe(404);
    await expect(response.json()).resolves.toMatchObject({ error: "unsupported_path" });
  });

  it("returns 403 when role is not allowed for the endpoint", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-viewer":"viewer"}');

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      method: "PUT",
      headers: {
        authorization: "Bearer token-viewer",
        "content-type": "application/json",
      },
      body: JSON.stringify({ version: "v1" }),
    });

    const { PUT } = await import("./route");
    const response = await PUT(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(403);
    await expect(response.json()).resolves.toMatchObject({ error: "forbidden" });
  });

  it("returns 503 when VERITAS_API_BASE_URL is not configured in production", async () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("VERITAS_API_BASE_URL", "");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: { authorization: "Bearer token-admin" },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toMatchObject({
      error: "server_misconfigured",
      detail: "VERITAS_API_BASE_URL must be configured in production.",
    });
  });

  it("proxies a successful GET request with content-type forwarding", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ policy: {} }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy?foo=bar", {
      headers: { authorization: "Bearer token-admin" },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledUrl = fetchMock.mock.calls[0]?.[0] as URL;
    expect(calledUrl.toString()).toContain("internal-api:8000/v1/governance/policy");
    expect(calledUrl.toString()).toContain("foo=bar");
    expect(response.headers.get("content-type")).toBe("application/json");
  });

  it("proxies a POST request with body", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const { POST } = await import("./route");
    const request = new NextRequest("http://localhost/api/veritas/v1/decide", {
      method: "POST",
      headers: {
        authorization: "Bearer token-admin",
        "content-type": "application/json",
      },
      body: JSON.stringify({ query: "test" }),
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["v1", "decide"] }),
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const calledInit = fetchMock.mock.calls[0]?.[1];
    expect(calledInit?.method).toBe("POST");
    expect(calledInit?.body).toContain("test");
    expect((calledInit?.headers as Headers).get("Content-Type")).toBe("application/json");
  });

  it("returns 413 when POST body exceeds 1MB", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const { POST } = await import("./route");
    const largeBody = "x".repeat(1024 * 1024 + 1);
    const request = new NextRequest("http://localhost/api/veritas/v1/decide", {
      method: "POST",
      headers: {
        authorization: "Bearer token-admin",
        "content-type": "application/json",
      },
      body: largeBody,
    });

    const response = await POST(request, {
      params: Promise.resolve({ path: ["v1", "decide"] }),
    });

    expect(response.status).toBe(413);
    await expect(response.json()).resolves.toMatchObject({ error: "payload_too_large" });
  });

  it("forwards trace-id header from request to upstream and response", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const fetchMock = vi.fn(async () =>
      new Response("{}", {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: {
        authorization: "Bearer token-admin",
        "x-trace-id": "my-trace-123",
      },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.headers.get("x-trace-id")).toBe("my-trace-123");
    const upstreamHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
    expect(upstreamHeaders.get("x-trace-id")).toBe("my-trace-123");
    expect(upstreamHeaders.get("X-Request-Id")).toBe("my-trace-123");
    expect(upstreamHeaders.get("X-Role")).toBe("admin");
  });

  it("forwards upstream content-type to client response", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const fetchMock = vi.fn(async () => {
      const resp = new Response('{"data":"ok"}', { status: 200 });
      // Overwrite with specific content-type
      Object.defineProperty(resp, "headers", {
        value: new Headers({ "content-type": "application/vnd.api+json" }),
      });
      return resp;
    });
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: { authorization: "Bearer token-admin" },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(200);
    expect(response.headers.get("content-type")).toBe("application/vnd.api+json");
  });

  it("returns auth error response with trace-id header", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: { "x-trace-id": "trace-abc" },
      // no auth header
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(401);
    expect(response.headers.get("x-trace-id")).toBe("trace-abc");
  });

  it("authenticates via cookie when no Authorization header", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "test-key");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"cookie-token":"admin"}');

    const fetchMock = vi.fn(async () =>
      new Response("{}", { status: 200, headers: { "content-type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: {
        cookie: "__veritas_bff=cookie-token",
      },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(200);
  });
});

describe("veritas bff route runtime api key resolution", () => {
  it("returns 503 when VERITAS_API_KEY is missing at request time", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_API_KEY", "");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const request = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: { authorization: "Bearer token-admin" },
    });

    const response = await GET(request, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(response.status).toBe(503);
    await expect(response.json()).resolves.toMatchObject({
      error: "server_misconfigured",
      detail: "VERITAS_API_KEY is not configured on server.",
    });
  });

  it("uses the latest VERITAS_API_KEY for each request", async () => {
    vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"token-admin":"admin"}');

    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    vi.stubEnv("VERITAS_API_KEY", "first-key");
    const firstRequest = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: { authorization: "Bearer token-admin" },
    });
    await GET(firstRequest, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    vi.stubEnv("VERITAS_API_KEY", "rotated-key");
    const secondRequest = new NextRequest("http://localhost/api/veritas/v1/governance/policy", {
      headers: { authorization: "Bearer token-admin" },
    });
    await GET(secondRequest, {
      params: Promise.resolve({ path: ["v1", "governance", "policy"] }),
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect((fetchMock.mock.calls[0]?.[1]?.headers as Headers).get("X-API-Key")).toBe("first-key");
    expect((fetchMock.mock.calls[1]?.[1]?.headers as Headers).get("X-API-Key")).toBe("rotated-key");
  });
});
