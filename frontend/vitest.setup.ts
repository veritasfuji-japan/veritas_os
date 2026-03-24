import "@testing-library/jest-dom/vitest";

// jsdom does not implement HTMLDialogElement.showModal / close.
// Provide no-op stubs so components using <dialog> render without errors.
if (typeof HTMLDialogElement !== "undefined") {
  if (!HTMLDialogElement.prototype.showModal) {
    HTMLDialogElement.prototype.showModal = function () {
      this.setAttribute("open", "");
    };
  }
  if (!HTMLDialogElement.prototype.close) {
    HTMLDialogElement.prototype.close = function () {
      this.removeAttribute("open");
    };
  }
}

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

const CANVAS_CONTEXT_STUB = {
  setTransform: () => undefined,
  clearRect: () => undefined,
  beginPath: () => undefined,
  arc: () => undefined,
  fill: () => undefined,
  fillStyle: "",
  globalAlpha: 1,
};

if (typeof HTMLCanvasElement !== "undefined") {
  Object.defineProperty(HTMLCanvasElement.prototype, "getContext", {
    configurable: true,
    value: () => CANVAS_CONTEXT_STUB,
  });
}
