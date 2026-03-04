import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.VERITAS_API_BASE_URL ?? process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ?? "http://localhost:8000";
const API_KEY = process.env.VERITAS_API_KEY ?? "";

/** Max request body size for proxied requests (1MB). */
const MAX_PROXY_BODY_BYTES = 1 * 1024 * 1024;

/**
 * Reject path segments that could cause path traversal or URL manipulation.
 * Blocks "..", empty segments, and segments with encoded slashes or null bytes.
 */
function hasUnsafeSegment(pathSegments: string[]): boolean {
  return pathSegments.some(
    (seg) => seg === ".." || seg === "." || seg === "" || /[%\x00/\\]/.test(seg),
  );
}

function buildTargetUrl(pathSegments: string[], searchParams: URLSearchParams): URL {
  const baseUrl = API_BASE.replace(/\/$/, "");
  const safePath = pathSegments.map(encodeURIComponent).join("/");
  return new URL(`${baseUrl}/${safePath}?${searchParams.toString()}`);
}

function isAllowedPath(pathSegments: string[], method: string): boolean {
  if (hasUnsafeSegment(pathSegments)) {
    return false;
  }

  const path = pathSegments.join("/");

  if (path === "v1/decide" && method === "POST") {
    return true;
  }

  if (path === "v1/governance/value-drift" && method === "GET") {
    return true;
  }

  if (path === "v1/governance/policy" && ["GET", "PUT"].includes(method)) {
    return true;
  }

  if (path === "v1/trust/logs" && method === "GET") {
    return true;
  }

  if (path.startsWith("v1/trust/") && pathSegments.length === 3 && method === "GET") {
    return true;
  }

  if (path === "v1/events" && method === "GET") {
    return true;
  }

  return false;
}

/**
 * Proxies allowed Veritas API calls from browser to backend using server-side API key.
 */
async function handleProxy(request: NextRequest, pathSegments: string[]): Promise<Response> {
  if (!isAllowedPath(pathSegments, request.method)) {
    return NextResponse.json({ error: "unsupported_path" }, { status: 404 });
  }

  if (!API_KEY.trim()) {
    return NextResponse.json(
      { error: "server_misconfigured", detail: "VERITAS_API_KEY is not configured on server." },
      { status: 503 },
    );
  }

  const targetUrl = buildTargetUrl(pathSegments, request.nextUrl.searchParams);
  const upstreamHeaders = new Headers();
  upstreamHeaders.set("X-API-Key", API_KEY.trim());

  const contentType = request.headers.get("content-type");
  if (contentType) {
    upstreamHeaders.set("Content-Type", contentType);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let body: string | undefined;
  if (hasBody) {
    body = await request.text();
    if (body.length > MAX_PROXY_BODY_BYTES) {
      return NextResponse.json({ error: "payload_too_large" }, { status: 413 });
    }
  }

  const upstreamResponse = await fetch(targetUrl, {
    method: request.method,
    headers: upstreamHeaders,
    body,
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  const upstreamContentType = upstreamResponse.headers.get("content-type");
  if (upstreamContentType) {
    responseHeaders.set("Content-Type", upstreamContentType);
  }

  return new Response(upstreamResponse.body, {
    status: upstreamResponse.status,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  return handleProxy(request, path);
}

export async function POST(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  return handleProxy(request, path);
}

export async function PUT(request: NextRequest, context: { params: Promise<{ path: string[] }> }): Promise<Response> {
  const { path } = await context.params;
  return handleProxy(request, path);
}
