import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET as session } from "../../auth/session/route";
import { POST } from "./route";

const ADMIN = "admin-session-test-only";
const VIEWER = "viewer-session-test-only";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe.each(["session", "privileged-proxy"] as const)("credential selection for %s", (endpoint) => {
  async function call(authorization: string | undefined, cookieToken = ADMIN) {
    vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", JSON.stringify({ [ADMIN]: "admin", [VIEWER]: "viewer" }));
    vi.stubEnv("VERITAS_API_BASE_URL", "http://upstream.test");
    vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "");
    vi.stubEnv("VERITAS_API_KEY", "backend-test-only");
    const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const headers = new Headers({ cookie: `__veritas_bff=${cookieToken}` });
    if (authorization !== undefined) headers.set("Authorization", authorization);
    const request = new NextRequest(`http://localhost/api/${endpoint === "session" ? "auth/session" : "veritas/v1/system/halt"}`, {
      headers, method: endpoint === "session" ? "GET" : "POST",
    });
    const response = endpoint === "session" ? await session(request) : await POST(request, {
      params: Promise.resolve({ path: ["v1", "system", "halt"] }),
    });
    return { response, fetchMock };
  }

  it.each([
    "", "Basic invalid-test-only", "Bearer", "Bearer ",
    `Bearer ${ADMIN} extra`, `Bearer\t${ADMIN}`, `Bearer ${ADMIN}, Bearer ${VIEWER}`,
  ])("rejects malformed Authorization instead of using the admin cookie: %j", async (header) => {
    const { response, fetchMock } = await call(header);
    expect(response.status).toBe(401);
    const payload = await response.json();
    expect(payload).toMatchObject({ error: "unauthorized" });
    expect(payload).not.toHaveProperty("role");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([`Bearer ${VIEWER}`, `bEaReR ${VIEWER}`, `Bearer  ${VIEWER}`])(
    "uses the explicit viewer credential even with an admin cookie: %s", async (header) => {
      const { response, fetchMock } = await call(header);
      if (endpoint === "session") {
        expect(response.status).toBe(200);
        expect(await response.json()).toEqual({ ok: true, role: "viewer" });
      } else {
        expect(response.status).toBe(403);
      }
      expect(fetchMock).not.toHaveBeenCalled();
    },
  );

  it("rejects an unknown Bearer token without using the admin cookie", async () => {
    const { response, fetchMock } = await call("Bearer removed-test-only");
    expect(response.status).toBe(403);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([undefined, `Bearer ${ADMIN}`])("preserves valid admin authentication: %j", async (header) => {
    const { response, fetchMock } = await call(header);
    expect(response.status).toBe(200);
    if (endpoint === "session") {
      expect(await response.json()).toEqual({ ok: true, role: "admin" });
      expect(fetchMock).not.toHaveBeenCalled();
    } else {
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  });
});
