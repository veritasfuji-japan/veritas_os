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
 * Name of the httpOnly cookie set by middleware for same-origin BFF auth.
 */
export const BFF_SESSION_COOKIE = "__veritas_bff";

/**
 * Resolve caller role from Authorization header or session cookie.
 *
 * Lookup order:
 * 1. `Authorization: Bearer <token>` header  (programmatic / external clients)
 * 2. `__veritas_bff` httpOnly cookie          (browser same-origin requests)
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

  // 1. Try Authorization header first
  const authorization = headers.get("authorization") ?? "";
  const [scheme, headerToken] = authorization.split(" ");
  if (scheme?.toLowerCase() === "bearer" && headerToken) {
    const role = tokenRoleMap.get(headerToken);
    if (role) {
      return { role };
    }
    return {
      errorResponse: NextResponse.json({ error: "forbidden" }, { status: 403 }),
    };
  }

  // 2. Fall back to httpOnly session cookie
  const cookieHeader = headers.get("cookie") ?? "";
  const sessionToken = parseCookieValue(cookieHeader, BFF_SESSION_COOKIE);
  if (sessionToken) {
    const role = tokenRoleMap.get(sessionToken);
    if (role) {
      return { role };
    }
    return {
      errorResponse: NextResponse.json({ error: "forbidden" }, { status: 403 }),
    };
  }

  return {
    errorResponse: NextResponse.json({ error: "unauthorized" }, { status: 401 }),
  };
}

/**
 * Extract a single cookie value by name from a raw `Cookie` header string.
 */
function parseCookieValue(cookieHeader: string, name: string): string | undefined {
  const match = cookieHeader
    .split(";")
    .map((s) => s.trim())
    .find((s) => s.startsWith(`${name}=`));
  return match ? match.slice(name.length + 1) : undefined;
}
