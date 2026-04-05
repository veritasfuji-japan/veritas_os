import { describe, it, expect, vi } from "vitest";
import { resolveTraceId, TRACE_ID_HEADER_NAME } from "./trace-id";

describe("resolveTraceId", () => {
  it("returns value from X-Trace-Id header", () => {
    const headers = new Headers({ [TRACE_ID_HEADER_NAME]: "trace-abc-12345678" });
    expect(resolveTraceId(headers)).toBe("trace-abc-12345678");
  });

  it("returns value from lowercase x-trace-id header", () => {
    const headers = new Headers({ "x-trace-id": "lowercase-trace-id" });
    expect(resolveTraceId(headers)).toBe("lowercase-trace-id");
  });

  it("returns value from X-Request-Id header when no trace id", () => {
    const headers = new Headers({ "X-Request-Id": "request-id-12345678" });
    expect(resolveTraceId(headers)).toBe("request-id-12345678");
  });

  it("generates UUID when no valid header is present", () => {
    const mockUUID = "550e8400-e29b-41d4-a716-446655440000";
    vi.spyOn(crypto, "randomUUID").mockReturnValueOnce(mockUUID as `${string}-${string}-${string}-${string}-${string}`);
    const headers = new Headers();
    expect(resolveTraceId(headers)).toBe(mockUUID);
  });

  it("rejects malformed trace IDs (too short)", () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValueOnce("fallback-uuid-0000" as `${string}-${string}-${string}-${string}-${string}`);
    const headers = new Headers({ [TRACE_ID_HEADER_NAME]: "short" });
    expect(resolveTraceId(headers)).toBe("fallback-uuid-0000");
  });

  it("rejects trace IDs starting with invalid characters", () => {
    vi.spyOn(crypto, "randomUUID").mockReturnValueOnce("fallback-uuid-0001" as `${string}-${string}-${string}-${string}-${string}`);
    // Starts with a space after trim is empty — falls through
    const headers = new Headers({ [TRACE_ID_HEADER_NAME]: "!!invalid-trace-id" });
    expect(resolveTraceId(headers)).toBe("fallback-uuid-0001");
  });

  it("trims whitespace from header values", () => {
    const headers = new Headers({ [TRACE_ID_HEADER_NAME]: "  valid-trace-id-123  " });
    expect(resolveTraceId(headers)).toBe("valid-trace-id-123");
  });
});
