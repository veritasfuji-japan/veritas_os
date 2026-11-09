/**
 * Decode a UTF-8 request body while enforcing a limit on received bytes.
 * Return null on overflow and stop consuming the stream.
 */
export async function readBoundedRequestText(
  request: Request,
  maxBytes: number,
): Promise<string | null> {
  if (!request.body) return "";

  const reader = request.body.getReader();
  const decoder = new TextDecoder();
  let size = 0;
  let text = "";
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) return text + decoder.decode();

      size += value.byteLength;
      if (size > maxBytes) {
        // A slow or failed cancellation must not delay the 413 response.
        void reader.cancel().catch(() => {});
        return null;
      }
      text += decoder.decode(value, { stream: true });
    }
  } finally {
    reader.releaseLock();
  }
}
