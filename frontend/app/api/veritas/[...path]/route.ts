import { NextRequest, NextResponse } from "next/server";

import {
  authenticateRoleFromHeaders,
  matchPolicy,
  parseAuthTokensConfig,
} from "./authz";
import { getBodySizeBytes } from "./body-size";

const API_BASE =
  process.env.VERITAS_API_BASE_URL ??
  process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ??
  "http://localhost:8000";
const API_KEY = process.env.VERITAS_API_KEY ?? "";

/** Max request body size for proxied requests (1MB). */
const MAX_PROXY_BODY_BYTES = 1 * 1024 * 1024;

function buildTargetUrl(pathSegments: string[], searchParams: URLSearchParams): URL {
  const baseUrl = API_BASE.replace(/\/$/, "");
  const safePath = pathSegments.map(encodeURIComponent).join("/");
  return new URL(`${baseUrl}/${safePath}?${searchParams.toString()}`);
}

/**
 * Proxies allowed Veritas API calls from browser to backend using server-side API key.
 */
async function handleProxy(request: NextRequest, pathSegments: string[]): Promise<Response> {
  const matched = matchPolicy(pathSegments, request.method);
  if (!matched) {
    return NextResponse.json({ error: "unsupported_path" }, { status: 404 });
  }

  const tokenRoleMap = parseAuthTokensConfig(process.env.VERITAS_BFF_AUTH_TOKENS_JSON);
  const authResult = authenticateRoleFromHeaders(request.headers, tokenRoleMap);
  if (authResult.errorResponse) {
    return authResult.errorResponse;
  }

  if (!authResult.role || !matched.policy.roles.includes(authResult.role)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
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
    if (getBodySizeBytes(body) > MAX_PROXY_BODY_BYTES) {
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

export async function GET(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  return handleProxy(request, path);
}

export async function POST(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  return handleProxy(request, path);
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const { path } = await context.params;
  return handleProxy(request, path);
}
