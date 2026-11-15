import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const EVENTS_URL = "http://localhost/api/veritas/v1/events";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

async function openEventStream(headers: HeadersInit) {
  vi.stubEnv("VERITAS_API_BASE_URL", "http://internal-api:8000");
  vi.stubEnv("VERITAS_API_KEY", "test-backend-key");
  vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", '{"stream-token":"operator","other-token":"viewer"}');

  const cancel = vi.fn();
  let source!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      source = controller;
    },
    cancel,
  });
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, {
    headers: { "Content-Type": "text/event-stream; charset=utf-8" },
  })));

  const response = await GET(new NextRequest(EVENTS_URL, { headers }), {
    params: Promise.resolve({ path: ["v1", "events"] }),
  });
  expect(response.status).toBe(200);

  return {
    reader: response.body!.getReader(),
    send: (data: string) => source.enqueue(new TextEncoder().encode(data)),
    cancel,
  };
}

describe("BFF SSE authentication", () => {
  it.each([
    ["revoked bearer", { Authorization: "Bearer stream-token" }, '{"other-token":"viewer"}'],
    ["changed cookie role", { Cookie: "__veritas_bff=stream-token" }, '{"stream-token":"viewer"}'],
  ] satisfies [string, HeadersInit, string][])(
    "closes the stream before forwarding another chunk for a %s",
    async (_label, headers, updatedConfig) => {
      const stream = await openEventStream(headers);
      const firstChunk = "data: first\n\n";
      stream.send(firstChunk);
      expect(new TextDecoder().decode((await stream.reader.read()).value)).toBe(firstChunk);

      const nextRead = stream.reader.read();
      vi.stubEnv("VERITAS_BFF_AUTH_TOKENS_JSON", updatedConfig);
      stream.send("data: next\n\n");

      await expect(nextRead).resolves.toEqual({ value: undefined, done: true });
      await vi.waitFor(() => expect(stream.cancel).toHaveBeenCalledOnce());
    },
  );

  it("propagates downstream cancellation to the upstream body", async () => {
    const stream = await openEventStream({ Authorization: "Bearer stream-token" });
    await stream.reader.cancel();
    await vi.waitFor(() => expect(stream.cancel).toHaveBeenCalledOnce());
  });
});
