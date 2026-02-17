const BACKEND_BASE_PATH = "/api";

/**
 * Build a same-origin API URL routed via Next.js rewrites.
 */
export function buildApiUrl(path: string): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${BACKEND_BASE_PATH}${normalized}`;
}
