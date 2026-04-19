import { describe, it, expect } from "vitest";
import {
  hasUnsafeSegment,
  parseAuthTokensConfig,
  matchPolicy,
  authenticateRoleFromHeaders,
} from "./route-auth";

describe("hasUnsafeSegment", () => {
  it("returns false for safe segments", () => {
    expect(hasUnsafeSegment(["v1", "governance", "policy"])).toBe(false);
  });

  it("returns true for path traversal (..)", () => {
    expect(hasUnsafeSegment(["v1", "..", "secret"])).toBe(true);
  });

  it("returns true for dot segment", () => {
    expect(hasUnsafeSegment(["v1", ".", "policy"])).toBe(true);
  });

  it("returns true for empty segments", () => {
    expect(hasUnsafeSegment(["v1", "", "policy"])).toBe(true);
  });

  it("returns true for encoded characters", () => {
    expect(hasUnsafeSegment(["v1", "%2e%2e"])).toBe(true);
  });

  it("returns true for null bytes", () => {
    expect(hasUnsafeSegment(["v1", "test\x00"])).toBe(true);
  });

  it("returns true for backslash", () => {
    expect(hasUnsafeSegment(["v1", "test\\path"])).toBe(true);
  });
});

describe("parseAuthTokensConfig", () => {
  it("returns empty map for undefined input", () => {
    expect(parseAuthTokensConfig(undefined).size).toBe(0);
  });

  it("returns empty map for empty string", () => {
    expect(parseAuthTokensConfig("").size).toBe(0);
  });

  it("returns empty map for whitespace-only string", () => {
    expect(parseAuthTokensConfig("   ").size).toBe(0);
  });

  it("parses valid token-role mapping", () => {
    const config = JSON.stringify({ tokenA: "viewer", tokenB: "admin", tokenC: "operator" });
    const result = parseAuthTokensConfig(config);
    expect(result.size).toBe(3);
    expect(result.get("tokenA")).toBe("viewer");
    expect(result.get("tokenB")).toBe("admin");
    expect(result.get("tokenC")).toBe("operator");
  });

  it("ignores unsupported role values", () => {
    const config = JSON.stringify({ tokenA: "viewer", tokenB: "superadmin" });
    const result = parseAuthTokensConfig(config);
    expect(result.size).toBe(1);
    expect(result.get("tokenA")).toBe("viewer");
  });

  it("returns empty map for invalid JSON", () => {
    expect(parseAuthTokensConfig("{invalid").size).toBe(0);
  });

  it("returns empty map for array JSON", () => {
    expect(parseAuthTokensConfig("[]").size).toBe(0);
  });

  it("ignores non-string values", () => {
    const config = JSON.stringify({ tokenA: "admin", tokenB: 123 });
    const result = parseAuthTokensConfig(config);
    expect(result.size).toBe(1);
  });
});

describe("matchPolicy", () => {
  it("matches GET governance/policy for viewer", () => {
    const result = matchPolicy(["v1", "governance", "policy"], "GET");
    expect(result).not.toBeNull();
    expect(result!.policy.roles).toContain("viewer");
  });

  it("matches PUT governance/policy for admin only", () => {
    const result = matchPolicy(["v1", "governance", "policy"], "PUT");
    expect(result).not.toBeNull();
    expect(result!.policy.roles).toEqual(["admin"]);
  });

  it("matches POST decide for operator/admin", () => {
    const result = matchPolicy(["v1", "decide"], "POST");
    expect(result).not.toBeNull();
    expect(result!.policy.roles).toContain("operator");
    expect(result!.policy.roles).toContain("admin");
  });

  it("returns null for unregistered path", () => {
    expect(matchPolicy(["v1", "unknown", "endpoint"], "GET")).toBeNull();
  });

  it("returns null for wrong method", () => {
    expect(matchPolicy(["v1", "decide"], "GET")).toBeNull();
  });

  it("returns null for unsafe segments", () => {
    expect(matchPolicy(["v1", "..", "decide"], "POST")).toBeNull();
  });

  it("normalizes method to uppercase", () => {
    const result = matchPolicy(["v1", "governance", "policy"], "get");
    expect(result).not.toBeNull();
  });

  it("matches trust log single item path", () => {
    const result = matchPolicy(["v1", "trust", "req-123"], "GET");
    expect(result).not.toBeNull();
  });

  it("matches WAT read endpoint for viewer", () => {
    const result = matchPolicy(["v1", "wat", "wat_123"], "GET");
    expect(result).not.toBeNull();
    expect(result!.policy.roles).toContain("viewer");
  });

  it("matches WAT mutate endpoint for operator/admin", () => {
    const result = matchPolicy(["v1", "wat", "issue-shadow"], "POST");
    expect(result).not.toBeNull();
    expect(result!.policy.roles).toContain("operator");
  });

  it("matches system halt for admin only", () => {
    const result = matchPolicy(["v1", "system", "halt"], "POST");
    expect(result).not.toBeNull();
    expect(result!.policy.roles).toEqual(["admin"]);
  });
});

describe("authenticateRoleFromHeaders", () => {
  const tokenMap = new Map([
    ["token-viewer", "viewer" as const],
    ["token-admin", "admin" as const],
  ]);

  it("returns 503 when tokenRoleMap is empty", () => {
    const headers = new Headers({ authorization: "Bearer some-token" });
    const result = authenticateRoleFromHeaders(headers, new Map());
    expect(result.errorResponse).toBeDefined();
  });

  it("authenticates via Bearer token", () => {
    const headers = new Headers({ authorization: "Bearer token-admin" });
    const result = authenticateRoleFromHeaders(headers, tokenMap);
    expect(result.role).toBe("admin");
    expect(result.errorResponse).toBeUndefined();
  });

  it("returns 403 for invalid Bearer token", () => {
    const headers = new Headers({ authorization: "Bearer invalid-token" });
    const result = authenticateRoleFromHeaders(headers, tokenMap);
    expect(result.errorResponse).toBeDefined();
    expect(result.role).toBeUndefined();
  });

  it("authenticates via session cookie", () => {
    const headers = new Headers({ cookie: "__veritas_bff=token-viewer; other=value" });
    const result = authenticateRoleFromHeaders(headers, tokenMap);
    expect(result.role).toBe("viewer");
  });

  it("returns 403 for invalid session cookie", () => {
    const headers = new Headers({ cookie: "__veritas_bff=bad-token" });
    const result = authenticateRoleFromHeaders(headers, tokenMap);
    expect(result.errorResponse).toBeDefined();
  });

  it("returns 401 when no credentials provided", () => {
    const headers = new Headers();
    const result = authenticateRoleFromHeaders(headers, tokenMap);
    expect(result.errorResponse).toBeDefined();
  });

  it("prefers Bearer token over cookie", () => {
    const headers = new Headers({
      authorization: "Bearer token-admin",
      cookie: "__veritas_bff=token-viewer",
    });
    const result = authenticateRoleFromHeaders(headers, tokenMap);
    expect(result.role).toBe("admin");
  });
});
