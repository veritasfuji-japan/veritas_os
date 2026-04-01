import { afterEach, describe, expect, it, vi } from "vitest";

import {
  buildCspEnforced,
  buildCspReportOnly,
  generateNonce,
  isProductionRuntime,
  middleware,
  resolveCspReportOnlyEndpoint,
  shouldIssueDefaultBffSessionCookie,
  shouldUseSecureCookie,
  shouldWarnInsecureCspReportOnlyEndpoint,
  shouldEnforceNonceCsp,
  shouldWarnInsecureProductionCspConfig,
} from "./middleware";

describe("middleware CSP", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });
  it("generates a nonce string", () => {
    const nonce = generateNonce();

    expect(nonce.length).toBeGreaterThan(10);
  });

  it("builds enforced CSP in compatibility mode with unsafe-inline script-src", () => {
    const csp = buildCspEnforced("sample-nonce", false);
    const scriptDirective = csp
      .split(";")
      .find((directive) => directive.trim().startsWith("script-src"));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'unsafe-inline'");
  });

  it("builds enforced CSP in strict mode without unsafe-inline in script-src", () => {
    const csp = buildCspEnforced("sample-nonce", true);
    const scriptDirective = csp
      .split(";")
      .find((directive) => directive.trim().startsWith("script-src"));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
  });

  it("builds nonce-based report-only CSP without unsafe-inline in script-src", () => {
    const csp = buildCspReportOnly("sample-nonce");
    const scriptDirective = csp
      .split(";")
      .find((directive) => directive.trim().startsWith("script-src"));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
    expect(csp).toContain("report-uri /api/veritas/csp-report");
  });

  it("uses configured report-only endpoint when explicitly provided", () => {
    vi.stubEnv("VERITAS_CSP_REPORT_ONLY_ENDPOINT", "/security/csp-report");

    expect(resolveCspReportOnlyEndpoint()).toBe("/security/csp-report");
    expect(buildCspReportOnly("sample-nonce")).toContain(
      "report-uri /security/csp-report",
    );
  });

  it("defaults nonce enforcement flag to false in non-production profile", () => {
    vi.stubEnv("VERITAS_ENV", "development");

    expect(shouldEnforceNonceCsp()).toBe(false);
  });

  it("enables nonce enforcement only when explicitly opted in", () => {
    vi.stubEnv("VERITAS_CSP_ENFORCE_NONCE", "true");

    expect(shouldEnforceNonceCsp()).toBe(true);
  });

  it("enables nonce enforcement in VERITAS production profile by default", () => {
    vi.stubEnv("VERITAS_ENV", "production");

    expect(shouldEnforceNonceCsp()).toBe(true);
  });

  it("does not enforce nonce from NODE_ENV=production alone", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_ENV", "");

    expect(shouldEnforceNonceCsp()).toBe(false);
  });

  it("allows temporary unsafe-inline compatibility override via explicit escape hatch", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT", "true");

    expect(shouldEnforceNonceCsp()).toBe(false);
  });

  it("warn helper returns true when production runtime enables unsafe-inline escape hatch", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT", "true");

    expect(shouldWarnInsecureProductionCspConfig()).toBe(true);
  });

  it("warn helper returns false for VERITAS production runtime without unsafe-inline escape hatch", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT", "false");

    expect(shouldWarnInsecureProductionCspConfig()).toBe(false);
  });

  it("warn helper returns true when NODE_ENV=production is used without strict rollout", () => {
    vi.stubEnv("VERITAS_ENV", "");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT", "false");

    expect(shouldWarnInsecureProductionCspConfig()).toBe(true);
  });

  it("warn helper returns false for unset report-only endpoint override", () => {
    expect(shouldWarnInsecureCspReportOnlyEndpoint()).toBe(false);
  });

  it("warn helper returns false for same-origin report-only endpoint override", () => {
    vi.stubEnv("VERITAS_CSP_REPORT_ONLY_ENDPOINT", "/security/csp-report");

    expect(shouldWarnInsecureCspReportOnlyEndpoint()).toBe(false);
  });

  it("warn helper returns true for cross-origin report-only endpoint override", () => {
    vi.stubEnv("VERITAS_CSP_REPORT_ONLY_ENDPOINT", "https://collector.example/csp");

    expect(shouldWarnInsecureCspReportOnlyEndpoint()).toBe(true);
  });

  it("detects production runtime from VERITAS_ENV", () => {
    vi.stubEnv("VERITAS_ENV", "production");

    expect(isProductionRuntime()).toBe(true);
  });

  it("detects production runtime from NODE_ENV", () => {
    vi.stubEnv("NODE_ENV", "production");

    expect(isProductionRuntime()).toBe(true);
  });

  it("does not treat development runtime as production", () => {
    vi.stubEnv("VERITAS_ENV", "development");
    vi.stubEnv("NODE_ENV", "development");

    expect(isProductionRuntime()).toBe(false);
  });

  it("allows shared BFF session cookie issuance in non-production", () => {
    vi.stubEnv("VERITAS_ENV", "development");
    vi.stubEnv("NODE_ENV", "development");

    expect(shouldIssueDefaultBffSessionCookie()).toBe(true);
  });

  it("denies shared BFF session cookie issuance in production by default", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_BFF_ALLOW_GLOBAL_SESSION_IN_PROD", "false");

    expect(shouldIssueDefaultBffSessionCookie()).toBe(false);
  });

  it("allows shared BFF session cookie issuance in production only with explicit override", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_BFF_ALLOW_GLOBAL_SESSION_IN_PROD", "true");

    expect(shouldIssueDefaultBffSessionCookie()).toBe(true);
  });

  it("sets CSP headers and forwards nonce to the Next.js request", () => {
    const response = middleware({ headers: new Headers() } as never);
    const csp = response.headers.get("Content-Security-Policy") ?? "";
    const cspReportOnly =
      response.headers.get("Content-Security-Policy-Report-Only") ?? "";
    const leakedNonce = response.headers.get("x-veritas-nonce");
    const forwardedNonce =
      response.headers.get("x-middleware-request-x-nonce") ?? "";

    const scriptDirective = csp
      .split(";")
      .find((directive) => directive.trim().startsWith("script-src"));
    const reportOnlyScriptDirective = cspReportOnly
      .split(";")
      .find((directive) => directive.trim().startsWith("script-src"));

    expect(leakedNonce).toBeNull();
    expect(scriptDirective).toContain("'unsafe-inline'");
    expect(forwardedNonce).not.toBe("");
    expect(reportOnlyScriptDirective).toContain(`'nonce-${forwardedNonce}'`);
    expect(reportOnlyScriptDirective).not.toContain("'unsafe-inline'");
  });

  it("uses x-forwarded-proto to determine secure cookie semantics", () => {
    const request = {
      headers: new Headers({ "x-forwarded-proto": "https" }),
      nextUrl: { protocol: "http:" },
    } as never;

    expect(shouldUseSecureCookie(request)).toBe(true);
  });

  it("falls back to request protocol for secure cookie semantics", () => {
    const request = {
      headers: new Headers(),
      nextUrl: { protocol: "https:" },
    } as never;

    expect(shouldUseSecureCookie(request)).toBe(true);
  });

  it("does not mint shared BFF cookie in production unless explicitly allowed", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "session-token");
    vi.stubEnv("VERITAS_BFF_ALLOW_GLOBAL_SESSION_IN_PROD", "false");

    const response = middleware({
      headers: new Headers({ "x-forwarded-proto": "https" }),
      cookies: { get: () => undefined },
      nextUrl: { protocol: "https:" },
    } as never);

    expect(response.cookies.get("__veritas_bff")).toBeUndefined();
  });

  it("mints shared BFF cookie with secure flag when explicitly allowed in production", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_BFF_SESSION_TOKEN", "session-token");
    vi.stubEnv("VERITAS_BFF_ALLOW_GLOBAL_SESSION_IN_PROD", "true");

    const response = middleware({
      headers: new Headers({ "x-forwarded-proto": "https" }),
      cookies: { get: () => undefined },
      nextUrl: { protocol: "http:" },
    } as never);

    const cookie = response.cookies.get("__veritas_bff");
    expect(cookie?.value).toBe("session-token");
    expect(cookie?.secure).toBe(true);
  });

  it("emits a security warning when NODE_ENV=production without CSP strict rollout", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT", "true");
    const warnSpy = vi
      .spyOn(console, "warn")
      .mockImplementation(() => undefined);

    middleware({ headers: new Headers() } as never);

    expect(warnSpy).toHaveBeenCalledTimes(1);
  });

  it("does not emit warning when production runtime keeps strict nonce CSP", () => {
    vi.stubEnv("VERITAS_ENV", "production");
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT", "false");
    const warnSpy = vi
      .spyOn(console, "warn")
      .mockImplementation(() => undefined);

    middleware({ headers: new Headers() } as never);

    expect(warnSpy).not.toHaveBeenCalled();
  });

  it("emits warning when report-only endpoint is cross-origin", () => {
    vi.stubEnv("VERITAS_CSP_REPORT_ONLY_ENDPOINT", "https://collector.example/csp");
    const warnSpy = vi
      .spyOn(console, "warn")
      .mockImplementation(() => undefined);

    middleware({ headers: new Headers() } as never);

    expect(warnSpy).toHaveBeenCalledTimes(1);
  });
});
