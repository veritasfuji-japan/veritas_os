import { describe, expect, it } from "vitest";

import {
  authenticateRoleFromHeaders,
  hasUnsafeSegment,
  matchPolicy,
  parseAuthTokensConfig,
} from "./authz";
import { getBodySizeBytes } from "./body-size";

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
    const governancePut = matchPolicy(["v1", "governance", "policy"], "PUT");
    const decidePost = matchPolicy(["v1", "decide"], "POST");

    expect(governancePut?.policy.roles).toEqual(["admin"]);
    expect(decidePost?.policy.roles).toEqual(["operator", "admin"]);
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
