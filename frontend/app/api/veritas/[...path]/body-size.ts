const TEXT_ENCODER = new TextEncoder();

/**
 * Calculate payload size using UTF-8 bytes to enforce byte-accurate limits.
 */
export function getBodySizeBytes(body: string): number {
  return TEXT_ENCODER.encode(body).length;
}
