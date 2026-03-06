import { NextResponse } from "next/server";

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
  {
    pathPattern: /^v1\/trust\/[^/]+$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/compliance\/config$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/compliance\/config$/,
    method: "PUT",
    roles: ["admin"],
  },
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

/**
 * Match API path/method against BFF route policy matrix.
 */
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
