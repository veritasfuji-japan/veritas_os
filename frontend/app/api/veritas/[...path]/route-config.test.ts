import { describe, it, expect, beforeEach, vi } from "vitest";
import { resolveApiBaseUrl, resetApiBaseUrlWarningStateForTest } from "./route-config";

describe("resolveApiBaseUrl", () => {
  const originalEnv = { ...process.env };

  beforeEach(() => {
    process.env = { ...originalEnv };
    delete process.env.VERITAS_API_BASE_URL;
    delete process.env.VERITAS_ENV;
    delete process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL;
    process.env.NODE_ENV = "test";
    resetApiBaseUrlWarningStateForTest();
  });

  it("returns VERITAS_API_BASE_URL when set", () => {
    process.env.VERITAS_API_BASE_URL = "https://api.example.com";
    expect(resolveApiBaseUrl()).toBe("https://api.example.com");
  });

  it("returns localhost fallback in non-production mode", () => {
    expect(resolveApiBaseUrl()).toBe("http://localhost:8000");
  });

  it("returns null in production when VERITAS_API_BASE_URL is missing", () => {
    process.env.VERITAS_ENV = "production";
    expect(resolveApiBaseUrl()).toBeNull();
  });

  it("returns null in production when NEXT_PUBLIC var is set (security block)", () => {
    process.env.VERITAS_ENV = "prod";
    process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL = "https://public.example.com";
    process.env.VERITAS_API_BASE_URL = "https://api.example.com";
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    expect(resolveApiBaseUrl()).toBeNull();
    warnSpy.mockRestore();
  });

  it("treats NODE_ENV=production as production mode", () => {
    process.env.NODE_ENV = "production";
    expect(resolveApiBaseUrl()).toBeNull();
  });

  it("trims whitespace from env values", () => {
    process.env.VERITAS_API_BASE_URL = "  https://api.example.com  ";
    expect(resolveApiBaseUrl()).toBe("https://api.example.com");
  });

  it("warns only once about NEXT_PUBLIC env var", () => {
    process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL = "https://public.example.com";
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    resolveApiBaseUrl();
    resolveApiBaseUrl();
    const securityWarnings = warnSpy.mock.calls.filter(
      (call) => typeof call[0] === "string" && call[0].includes("[security-warning]"),
    );
    expect(securityWarnings).toHaveLength(1);
    warnSpy.mockRestore();
  });
});
