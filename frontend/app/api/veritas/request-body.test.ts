import { describe, expect, it, vi } from "vitest";
import { readBoundedRequestText } from "./request-body";

describe("readBoundedRequestText", () => {
  it("cancels before reading the remainder of an oversized stream", async () => {
    const cancel = vi.fn();
    const pull = vi.fn((controller: ReadableStreamDefaultController<Uint8Array>) => {
      controller.enqueue(new Uint8Array(4));
    });
    const body = new ReadableStream({ pull, cancel }, { highWaterMark: 0 });

    await expect(readBoundedRequestText({ body } as Request, 7)).resolves.toBeNull();
    expect(pull).toHaveBeenCalledTimes(2);
    expect(cancel).toHaveBeenCalledOnce();
  });

  it("decodes split UTF-8 characters at the exact byte limit", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(Uint8Array.of(0xe3, 0x81));
        controller.enqueue(Uint8Array.of(0x82));
        controller.close();
      },
    });

    await expect(readBoundedRequestText({ body } as Request, 3)).resolves.toBe("あ");
  });
});
