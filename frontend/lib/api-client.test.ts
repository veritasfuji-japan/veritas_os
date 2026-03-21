import { describe, it, expect, vi, afterEach } from "vitest";
import {
  veritasFetch,
  veritasFetchWithOptions,
  ApiError,
  classifyHttpStatus,
  devLog,
} from "./api-client";

describe("classifyHttpStatus", () => {
  it("classifies 401 as auth", () => {
    expect(classifyHttpStatus(401)).toBe("auth");
  });

  it("classifies 403 as auth", () => {
    expect(classifyHttpStatus(403)).toBe("auth");
  });

  it("classifies 400 as validation", () => {
    expect(classifyHttpStatus(400)).toBe("validation");
  });

  it("classifies 422 as validation", () => {
    expect(classifyHttpStatus(422)).toBe("validation");
  });

  it("classifies 500 as server", () => {
    expect(classifyHttpStatus(500)).toBe("server");
  });

  it("classifies 502 as server", () => {
    expect(classifyHttpStatus(502)).toBe("server");
  });

  it("classifies 404 as unknown", () => {
    expect(classifyHttpStatus(404)).toBe("unknown");
  });
});

describe("ApiError", () => {
  it("has correct properties", () => {
    const err = new ApiError("test", "auth", 401, "trace-123");
    expect(err.message).toBe("test");
    expect(err.kind).toBe("auth");
    expect(err.status).toBe(401);
    expect(err.traceId).toBe("trace-123");
    expect(err.name).toBe("ApiError");
    expect(err).toBeInstanceOf(Error);
  });
});

describe("veritasFetch", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("includes same-origin credentials", async () => {
    const mockFetch = vi.fn().mockResolvedValue(new Response("ok"));
    globalThis.fetch = mockFetch;

    await veritasFetch("/api/veritas/v1/test");

    expect(mockFetch).toHaveBeenCalledOnce();
    expect(mockFetch.mock.calls[0][1]).toMatchObject({
      credentials: "same-origin",
    });
  });

  it("throws DOMException on timeout (backward compat)", async () => {
    globalThis.fetch = vi.fn().mockImplementation(
      () =>
        new Promise((_, reject) => {
          setTimeout(() => reject(new DOMException("aborted", "AbortError")), 10);
        }),
    );

    await expect(veritasFetch("/api/test", {}, 5)).rejects.toThrow(DOMException);
  });

  it("returns response on success", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    const res = await veritasFetch("/api/veritas/v1/test");
    expect(res.ok).toBe(true);
  });
});

describe("veritasFetchWithOptions", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("retries on 503 status", async () => {
    let callCount = 0;
    globalThis.fetch = vi.fn().mockImplementation(() => {
      callCount++;
      if (callCount === 1) {
        return Promise.resolve(new Response("error", { status: 503 }));
      }
      return Promise.resolve(new Response("ok", { status: 200 }));
    });

    const res = await veritasFetchWithOptions("/api/test", { retries: 1 });
    expect(res.ok).toBe(true);
    expect(callCount).toBe(2);
  });

  it("throws ApiError on network failure after retries exhausted", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(
      veritasFetchWithOptions("/api/test", { retries: 1, timeoutMs: 100 }),
    ).rejects.toThrow(ApiError);
    try {
      await veritasFetchWithOptions("/api/test", { retries: 0, timeoutMs: 100 });
    } catch (e) {
      expect((e as ApiError).kind).toBe("network");
    }
  });

  it("classifies timeout aborts as timeout errors", async () => {
    globalThis.fetch = vi.fn().mockImplementation(
      (_, init?: RequestInit) =>
        new Promise((_, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );

    await expect(
      veritasFetchWithOptions("/api/test", { timeoutMs: 5 }),
    ).rejects.toMatchObject({ kind: "timeout" });
  });

  it("classifies caller aborts as cancelled errors", async () => {
    const controller = new AbortController();
    globalThis.fetch = vi.fn().mockImplementation(
      (_, init?: RequestInit) =>
        new Promise((_, reject) => {
          init?.signal?.addEventListener("abort", () => {
            reject(new DOMException("aborted", "AbortError"));
          });
        }),
    );

    const pending = veritasFetchWithOptions("/api/test", {
      init: { signal: controller.signal },
      timeoutMs: 100,
    });
    controller.abort("user-cancelled");

    await expect(pending).rejects.toMatchObject({ kind: "cancelled" });
  });
});

describe("devLog", () => {
  it("does not throw in any environment", () => {
    expect(() => devLog("info", "test", { foo: "bar" })).not.toThrow();
    expect(() => devLog("warn", "test", { foo: "bar" })).not.toThrow();
    expect(() => devLog("error", "test", { foo: "bar" })).not.toThrow();
  });
});
