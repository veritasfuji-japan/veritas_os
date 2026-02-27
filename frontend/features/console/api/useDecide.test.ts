import { renderHook, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { useDecide } from "./useDecide";

type DecidePayload = Record<string, unknown>;

function buildDecidePayload(requestId: string, decision: string): DecidePayload {
  return {
    ok: true,
    error: null,
    request_id: requestId,
    version: "test",
    chosen: {},
    alternatives: [],
    options: [],
    decision_status: "allow",
    rejection_reason: null,
    values: null,
    telos_score: 0.5,
    fuji: {},
    gate: {
      risk: 0.1,
      telos_score: 0.5,
      decision_status: "allow",
      modifications: [],
    },
    evidence: [],
    critique: [],
    debate: [],
    extras: { decision },
    plan: null,
    planner: null,
    persona: {},
    memory_citations: [],
    memory_used_count: 0,
    trust_log: null,
  };
}

function createDeferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("useDecide", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("aborts an in-flight request when a new runDecision starts", async () => {
    const first = createDeferred<Response>();
    const secondPayload = buildDecidePayload("req-2", "latest");

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementationOnce((_input, init) => {
        const signal = init?.signal as AbortSignal;
        return new Promise<Response>((_resolve, reject) => {
          signal.addEventListener("abort", () => {
            reject(new DOMException("Aborted", "AbortError"));
          });
          void first.promise;
        });
      })
      .mockResolvedValueOnce(
        new Response(JSON.stringify(secondPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );

    vi.stubGlobal("fetch", fetchMock);

    const setQuery = vi.fn();
    const setResult = vi.fn();
    const setChatMessages = vi.fn();

    const { result } = renderHook(() =>
      useDecide({
        t: (_ja, en) => en,
        query: "q",
        setQuery,
        setResult,
        setChatMessages,
      }),
    );

    await act(async () => {
      void result.current.runDecision("first");
      await Promise.resolve();
      await result.current.runDecision("second");
    });

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(setResult).toHaveBeenCalledWith(secondPayload);
  });

  it("ignores stale completion and only applies latest result", async () => {
    const first = createDeferred<Response>();
    const second = createDeferred<Response>();

    const firstPayload = buildDecidePayload("req-1", "old");
    const secondPayload = buildDecidePayload("req-2", "new");

    const fetchMock = vi
      .fn<typeof fetch>()
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise);

    vi.stubGlobal("fetch", fetchMock);

    const setQuery = vi.fn();
    const setResult = vi.fn();
    const setChatMessages = vi.fn();

    const { result } = renderHook(() =>
      useDecide({
        t: (_ja, en) => en,
        query: "q",
        setQuery,
        setResult,
        setChatMessages,
      }),
    );

    await act(async () => {
      void result.current.runDecision("first");
      await Promise.resolve();
      void result.current.runDecision("second");
      second.resolve(
        new Response(JSON.stringify(secondPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      await Promise.resolve();
      first.resolve(
        new Response(JSON.stringify(firstPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      await Promise.resolve();
    });

    expect(setResult).toHaveBeenCalledTimes(1);
    expect(setResult).toHaveBeenCalledWith(secondPayload);
  });
});
