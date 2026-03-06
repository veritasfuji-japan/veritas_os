import { NextRequest, NextResponse } from "next/server";

import { getBodySizeBytes } from "./body-size";

const API_BASE =
  process.env.VERITAS_API_BASE_URL ??
  process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL ??
  "http://localhost:8000";
const API_KEY = process.env.VERITAS_API_KEY ?? "";

/** Max request body size for proxied requests (1MB). */
const MAX_PROXY_BODY_BYTES = 1 * 1024 * 1024;

const SUPPORTED_BFF_ROLES = ["viewer", "operator", "admin"] as const;

export type BffRole = (typeof SUPPORTED_BFF_ROLES)[number];

interface RoutePolicy {
  readonly pathPattern: RegExp;
  readonly method: "GET" | "POST" | "PUT";
  readonly roles: readonly BffRole[];
}

interface MatchedPolicy {
  readonly policy: RoutePolicy;
  readonly path: string;
}

const ROUTE_POLICIES: readonly RoutePolicy[] = [
  { pathPattern: /^v1\/decide$/, method: "POST", roles: ["operator", "admin"] },
  {
    pathPattern: /^v1\/governance\/value-drift$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/governance\/policy$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  { pathPattern: /^v1\/governance\/policy$/, method: "PUT", roles: ["admin"] },
  {
    pathPattern: /^v1\/trust\/logs$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  { pathPattern: /^v1\/trust\/[^/]+$/, method: "GET", roles: ["viewer", "operator", "admin"] },
  { pathPattern: /^v1\/events$/, method: "GET", roles: ["viewer", "operator", "admin"] },
];

/**
 * Reject path segments that could cause path traversal or URL manipulation.
 * Blocks "..", empty segments, and segments with encoded slashes or null bytes.
 */
export function hasUnsafeSegment(pathSegments: string[]): boolean {
  return pathSegments.some(
    (seg) => seg === ".." || seg === "." || seg === "" || /[%\x00/\\]/.test(seg),
  );
}

function buildTargetUrl(pathSegments: string[], searchParams: URLSearchParams): URL {
  const baseUrl = API_BASE.replace(/\/$/, "");
  const safePath = pathSegments.map(encodeURIComponent).join("/");
  return new URL(`${baseUrl}/${safePath}?${searchParams.toString()}`);
}

/**
 * Parse token-role mapping from `VERITAS_BFF_AUTH_TOKENS_JSON`.
 * Expected format: {"tokenA":"viewer","tokenB":"admin"}.
 */
export function parseAuthTokensConfig(rawConfig: string | undefined): Map<string, BffRole> {
  if (!rawConfig || !rawConfig.trim()) {
    return new Map();
  }

  try {
    const parsed = JSON.parse(rawConfig) as Record<string, unknown>;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      return new Map();
    }

    const entries = Object.entries(parsed).filter(([, value]) =>
      typeof value === "string" && SUPPORTED_BFF_ROLES.includes(value as BffRole),
    ) as Array<[string, BffRole]>;

    return new Map(entries);
  } catch {
    return new Map();
  }
}

export function matchPolicy(pathSegments: string[], method: string): MatchedPolicy | null {
  if (hasUnsafeSegment(pathSegments)) {
    return null;
  }

  const path = pathSegments.join("/");
  const normalizedMethod = method.toUpperCase();

  const policy = ROUTE_POLICIES.find(
    (candidate) =>
      candidate.method === normalizedMethod &&
      candidate.pathPattern.test(path) &&
      path.split("/").length === pathSegments.length,
  );

  if (!policy) {
    return null;
  }

  return { policy, path };
}

/**
 * Resolve caller role from Authorization header and token map.
 */
export function authenticateRoleFromHeaders(
  headers: Headers,
  tokenRoleMap: Map<string, BffRole>,
): { readonly role?: BffRole; readonly errorResponse?: NextResponse } {
  if (tokenRoleMap.size === 0) {
    return {
      errorResponse: NextResponse.json(
        {
          error: "server_misconfigured",
          detail:
            "VERITAS_BFF_AUTH_TOKENS_JSON must be configured with bearer token to role mapping.",
        },
        { status: 503 },
      ),
    };
  }

  const authorization = headers.get("authorization") ?? "";
  const [scheme, token] = authorization.split(" ");

  if (scheme?.toLowerCase() !== "bearer" || !token) {
    return {
      errorResponse: NextResponse.json({ error: "unauthorized" }, { status: 401 }),
    };
  }

  const role = tokenRoleMap.get(token);
  if (!role) {
    return {
      errorResponse: NextResponse.json({ error: "forbidden" }, { status: 403 }),
    };
  }

  return { role };
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
