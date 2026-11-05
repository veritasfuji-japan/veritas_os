import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET, POST, PUT } from "./route";

const ADMIN_ROUTES = [
  { method: "GET", path: ["v1", "governance", "policy"] },
  { method: "PUT", path: ["v1", "governance", "policy"] },
  { method: "POST", path: ["v1", "governance", "policy-bundles", "promote"] },
  { method: "PUT", path: ["v1", "compliance", "config"] },
  { method: "POST", path: ["v1", "system", "halt"] },
  { method: "POST", path: ["v1", "system", "resume"] },
] as const;
const HANDLERS = { GET, POST, PUT };

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe.each(["bearer", "cookie"] as const)("privileged BFF calls with %s authentication", (credential) => {
  describe.each(["viewer", "operator", "admin"] as const)("%s session", (role) => {
    it.each(ADMIN_ROUTES)("enforces admin before forwarding $method $path", async ({ method, path }) => {
      vi.stubEnv("VERITAS_API_BASE_URL", "http://upstream.test");
      vi.stubEnv("NEXT_PUBLIC_VERITAS_API_BASE_URL", "");
      vi.stubEnv("VERITAS_API_KEY", "shared-backend-test-only");
      vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", JSON.stringify({
        "viewer-test-only": "viewer", "operator-test-only": "operator", "admin-test-only": "admin",
      }));
      const fetchMock = vi.fn<typeof fetch>().mockResolvedValue(new Response("{}", { status: 200 }));
      vi.stubGlobal("fetch", fetchMock);
      const headers: Record<string, string> = {
        "X-Role": "admin", "X-API-Key": "caller-controlled-test-only",
        "Content-Type": "application/json",
      };
      if (credential === "bearer") headers.authorization = `Bearer ${role}-test-only`;
      else headers.cookie = `__veritas_bff=${role}-test-only`;
      const request = new NextRequest(`http://localhost/api/veritas/${path.join("/")}`, {
        method, headers, ...(method === "GET" ? {} : { body: JSON.stringify({ role: "admin" }) }),
      });
      const response = await HANDLERS[method](request, { params: Promise.resolve({ path: [...path] }) });
      if (role !== "admin") {
        expect(response.status).toBe(403);
        expect(await response.json()).toMatchObject({ error: "forbidden" });
        expect(fetchMock).not.toHaveBeenCalled();
      } else {
        expect(response.status).toBe(200);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const upstreamHeaders = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
        expect(upstreamHeaders.get("X-API-Key")).toBe("shared-backend-test-only");
        expect(upstreamHeaders.get("X-Role")).toBe("admin");
        expect(upstreamHeaders.has("Authorization")).toBe(false);
        expect(upstreamHeaders.has("Cookie")).toBe(false);
      }
    });
  });
});
