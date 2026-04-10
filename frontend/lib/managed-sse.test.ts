import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startManagedEventStream } from "./managed-sse";

class MockEventSource {
  public static instances: MockEventSource[] = [];
  public onopen: (() => void) | null = null;
  public onmessage: ((event: MessageEvent<string>) => void) | null = null;
  public onerror: (() => void) | null = null;
  public closed = false;

  constructor(
    public readonly url: string,
    public readonly init?: EventSourceInit,
  ) {
    MockEventSource.instances.push(this);
  }

  close(): void {
    this.closed = true;
  }
}

describe("startManagedEventStream", () => {
  const originalFetch = globalThis.fetch;
  const originalEventSource = globalThis.EventSource;

  beforeEach(() => {
    vi.useFakeTimers();
    MockEventSource.instances = [];
    (globalThis as Record<string, unknown>).EventSource = MockEventSource;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    globalThis.EventSource = originalEventSource;
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("waits before reconnecting when auth probe returns 401", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("unauthorized", { status: 401 }))
      .mockResolvedValueOnce(new Response("ok", { status: 200 }));

    const onAuthPause = vi.fn();
    const stop = startManagedEventStream("/api/veritas/v1/events", {
      onMessage: () => undefined,
      onAuthPause,
    });

    await Promise.resolve();
    expect(MockEventSource.instances).toHaveLength(0);
    expect(onAuthPause).toHaveBeenCalledTimes(1);

    await vi.advanceTimersByTimeAsync(60_000);
    expect(MockEventSource.instances).toHaveLength(1);

    stop();
  });

  it("ignores repeated onerror callbacks from a stale EventSource instance", async () => {
    const randomSpy = vi.spyOn(Math, "random").mockReturnValue(0);
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(new Response("ok", { status: 200 }))
      .mockResolvedValueOnce(new Response("ok", { status: 200 }));

    const stop = startManagedEventStream("/api/veritas/v1/events", {
      onMessage: () => undefined,
    });

    await Promise.resolve();
    expect(MockEventSource.instances).toHaveLength(1);

    const firstEventSource = MockEventSource.instances[0];
    firstEventSource?.onerror?.();
    firstEventSource?.onerror?.();

    await vi.advanceTimersByTimeAsync(800);
    await Promise.resolve();

    expect(MockEventSource.instances).toHaveLength(2);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);

    randomSpy.mockRestore();
    stop();
  });

  it("opens EventSource with same-origin credentials", async () => {
    globalThis.fetch = vi.fn().mockResolvedValue(new Response("ok", { status: 200 }));

    const stop = startManagedEventStream("/api/veritas/v1/events", {
      onMessage: () => undefined,
    });

    await vi.runOnlyPendingTimersAsync();

    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0]?.init).toMatchObject({ withCredentials: true });

    stop();
  });
});
