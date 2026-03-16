import { NextRequest, NextResponse } from "next/server";

import {
  authenticateRoleFromHeaders,
  matchPolicy,
  parseAuthTokensConfig,
} from "./route-auth";
import { getBodySizeBytes } from "./body-size";
import { resolveTraceId, TRACE_ID_HEADER_NAME } from "./trace-id";

import { resolveApiBaseUrl } from "./route-config";

const API_BASE = resolveApiBaseUrl();
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
  const traceId = resolveTraceId(request.headers);

  const matched = matchPolicy(pathSegments, request.method);
  if (!matched) {
    return NextResponse.json(
      { error: "unsupported_path", trace_id: traceId },
      {
        status: 404,
        headers: {
          [TRACE_ID_HEADER_NAME]: traceId,
        },
      },
    );
  }

  const tokenRoleMap = parseAuthTokensConfig(process.env.VERITAS_BFF_AUTH_TOKENS_JSON);
  const authResult = authenticateRoleFromHeaders(request.headers, tokenRoleMap);
  if (authResult.errorResponse) {
    authResult.errorResponse.headers.set(TRACE_ID_HEADER_NAME, traceId);
    return authResult.errorResponse;
  }

  if (!authResult.role || !matched.policy.roles.includes(authResult.role)) {
    return NextResponse.json(
      { error: "forbidden", trace_id: traceId },
      {
        status: 403,
        headers: {
          [TRACE_ID_HEADER_NAME]: traceId,
        },
      },
    );
  }

  if (!API_KEY.trim()) {
    return NextResponse.json(
      {
        error: "server_misconfigured",
        detail: "VERITAS_API_KEY is not configured on server.",
        trace_id: traceId,
      },
      {
        status: 503,
        headers: {
          [TRACE_ID_HEADER_NAME]: traceId,
        },
      },
    );
  }

  const targetUrl = buildTargetUrl(pathSegments, request.nextUrl.searchParams);
  const upstreamHeaders = new Headers();
  upstreamHeaders.set("X-API-Key", API_KEY.trim());
  upstreamHeaders.set(TRACE_ID_HEADER_NAME, traceId);
  upstreamHeaders.set("X-Request-Id", traceId);

  const contentType = request.headers.get("content-type");
  if (contentType) {
    upstreamHeaders.set("Content-Type", contentType);
  }

  const hasBody = !["GET", "HEAD"].includes(request.method);
  let body: string | undefined;
  if (hasBody) {
    body = await request.text();
    if (getBodySizeBytes(body) > MAX_PROXY_BODY_BYTES) {
      return NextResponse.json(
        { error: "payload_too_large", trace_id: traceId },
        {
          status: 413,
          headers: {
            [TRACE_ID_HEADER_NAME]: traceId,
          },
        },
      );
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
  responseHeaders.set(TRACE_ID_HEADER_NAME, traceId);

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
