/**
 * CSP violation report collection endpoint.
 *
 * Handles browser-sent Content-Security-Policy violation reports so that the
 * `report-uri /api/veritas/csp-report` directive in the report-only CSP header
 * no longer produces 404 errors.
 *
 * Supported payload formats:
 * - Legacy `application/csp-report` (single `{"csp-report": {...}}` object)
 * - Modern Reporting API `application/reports+json` (array of report objects)
 * - Fallback `application/json` for non-standard user agents
 *
 * Security notes:
 * - No authentication required (browsers send CSP reports automatically).
 * - Payload size is bounded to prevent abuse.
 * - Raw violation URIs are truncated in production to avoid leaking internal
 *   topology through verbose log output.
 */

import { NextRequest } from "next/server";

/** Maximum CSP report payload size (64 KB). */
const MAX_REPORT_BODY_BYTES = 64 * 1024;

/** Maximum length for URI values logged in production. */
const PROD_URI_TRUNCATE_LENGTH = 120;

/** Deduplication window in milliseconds (60 s). */
const DEDUP_WINDOW_MS = 60_000;

/** Maximum number of dedup keys retained before eviction. */
const DEDUP_MAX_KEYS = 256;

/**
 * In-memory dedup map: fingerprint → last-seen timestamp.
 *
 * Keeps log noise low during local development where the same violation fires
 * on every page load.  The map is bounded to avoid unbounded growth.
 */
const recentReports = new Map<string, number>();

interface NormalizedViolation {
  readonly directive: string;
  readonly blockedUri: string;
  readonly documentUri: string;
  readonly sourceFile: string;
}

/**
 * Returns whether the runtime should be treated as production.
 */
function isProduction(): boolean {
  const veritasEnv = (process.env.VERITAS_ENV ?? "").toLowerCase();
  const nodeEnv = (process.env.NODE_ENV ?? "").toLowerCase();
  return (
    veritasEnv === "prod" ||
    veritasEnv === "production" ||
    nodeEnv === "production"
  );
}

/**
 * Extract a compact violation summary from either legacy or modern CSP report
 * payloads.  Returns `null` when the payload is unparseable.
 */
export function normalizeViolation(
  body: unknown,
): NormalizedViolation | null {
  if (!body || typeof body !== "object") {
    return null;
  }

  // Legacy format: {"csp-report": { ... }}
  const legacy = (body as Record<string, unknown>)["csp-report"];
  if (legacy && typeof legacy === "object") {
    const report = legacy as Record<string, unknown>;
    return {
      directive: String(report["violated-directive"] ?? report["effective-directive"] ?? ""),
      blockedUri: String(report["blocked-uri"] ?? ""),
      documentUri: String(report["document-uri"] ?? ""),
      sourceFile: String(report["source-file"] ?? ""),
    };
  }

  // Modern Reporting API format: [{ type: "csp-violation", body: { ... } }]
  if (Array.isArray(body) && body.length > 0) {
    const first = body[0] as Record<string, unknown>;
    const reportBody =
      first?.body && typeof first.body === "object"
        ? (first.body as Record<string, unknown>)
        : first;
    return {
      directive: String(reportBody?.["effectiveDirective"] ?? reportBody?.["violatedDirective"] ?? ""),
      blockedUri: String(reportBody?.["blockedURL"] ?? reportBody?.["blockedUri"] ?? ""),
      documentUri: String(reportBody?.["documentURL"] ?? reportBody?.["documentUri"] ?? ""),
      sourceFile: String(reportBody?.["sourceFile"] ?? ""),
    };
  }

  // Flat object fallback (non-standard agents)
  const flat = body as Record<string, unknown>;
  if (flat["effective-directive"] || flat["effectiveDirective"] || flat["violated-directive"]) {
    return {
      directive: String(flat["effective-directive"] ?? flat["effectiveDirective"] ?? flat["violated-directive"] ?? ""),
      blockedUri: String(flat["blocked-uri"] ?? flat["blockedURL"] ?? ""),
      documentUri: String(flat["document-uri"] ?? flat["documentURL"] ?? ""),
      sourceFile: String(flat["source-file"] ?? flat["sourceFile"] ?? ""),
    };
  }

  return null;
}

/**
 * Build a deduplication fingerprint from a normalized violation.
 */
function fingerprint(v: NormalizedViolation): string {
  return `${v.directive}|${v.blockedUri}|${v.sourceFile}`;
}

/**
 * Truncate a URI string for safe logging in production.
 */
function truncateUri(uri: string, maxLen: number): string {
  if (uri.length <= maxLen) {
    return uri;
  }
  return `${uri.slice(0, maxLen)}…`;
}

/**
 * Evict stale entries from the dedup map and enforce size cap.
 */
function evictStaleEntries(now: number): void {
  for (const [key, ts] of recentReports) {
    if (now - ts > DEDUP_WINDOW_MS) {
      recentReports.delete(key);
    }
  }
  // Hard cap: drop oldest entries if still over limit
  if (recentReports.size > DEDUP_MAX_KEYS) {
    const sorted = [...recentReports.entries()].sort((a, b) => a[1] - b[1]);
    const toRemove = sorted.slice(0, sorted.length - DEDUP_MAX_KEYS);
    for (const [key] of toRemove) {
      recentReports.delete(key);
    }
  }
}

/**
 * Returns true if this violation was already logged within the dedup window.
 */
function isDuplicate(fp: string, now: number): boolean {
  const lastSeen = recentReports.get(fp);
  if (lastSeen !== undefined && now - lastSeen < DEDUP_WINDOW_MS) {
    return true;
  }
  recentReports.set(fp, now);
  return false;
}

/**
 * Reset internal dedup state.  Exported only for tests.
 */
export function resetDedupStateForTest(): void {
  recentReports.clear();
}

export async function POST(request: NextRequest): Promise<Response> {
  // Bound payload size
  const contentLength = request.headers.get("content-length");
  if (contentLength) {
    const size = parseInt(contentLength, 10);
    if (!Number.isNaN(size) && size > MAX_REPORT_BODY_BYTES) {
      return new Response(null, { status: 413 });
    }
  }

  let body: unknown;
  try {
    const rawText = await request.text();
    if (rawText.length > MAX_REPORT_BODY_BYTES) {
      return new Response(null, { status: 413 });
    }
    body = rawText ? JSON.parse(rawText) : null;
  } catch {
    // Malformed JSON — accept silently (don't penalize the browser)
    return new Response(null, { status: 204 });
  }

  const violation = normalizeViolation(body);
  if (!violation) {
    // Unrecognised format — accept without logging
    return new Response(null, { status: 204 });
  }

  const now = Date.now();
  evictStaleEntries(now);
  const fp = fingerprint(violation);

  if (!isDuplicate(fp, now)) {
    const prod = isProduction();
    const directive = violation.directive || "(unknown)";
    const blocked = prod
      ? truncateUri(violation.blockedUri, PROD_URI_TRUNCATE_LENGTH)
      : violation.blockedUri;
    const doc = prod
      ? truncateUri(violation.documentUri, PROD_URI_TRUNCATE_LENGTH)
      : violation.documentUri;

    console.info(
      `[csp-violation] directive=${directive} blocked=${blocked} document=${doc}`,
    );
  }

  return new Response(null, { status: 204 });
}
