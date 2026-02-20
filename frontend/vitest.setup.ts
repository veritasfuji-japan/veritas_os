import "@testing-library/jest-dom/vitest";

// Provide a global EventSource stub for jsdom (which doesn't have SSE support)
if (typeof globalThis.EventSource === "undefined") {
  class MockEventSource {
    url: string;
    onopen: (() => void) | null = null;
    onmessage: ((event: MessageEvent<string>) => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(url: string) {
      this.url = url;
    }
    close(): void {
      // no-op
    }
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (globalThis as any).EventSource = MockEventSource;
}
