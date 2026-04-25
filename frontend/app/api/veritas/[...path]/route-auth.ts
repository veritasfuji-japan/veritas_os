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
  // Decision
  { pathPattern: /^v1\/decide$/, method: "POST", roles: ["operator", "admin"] },

  // Governance
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
    pathPattern: /^v1\/governance\/policy\/history$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/governance\/policy-bundles\/promote$/,
    method: "POST",
    roles: ["admin"],
  },
  {
    pathPattern: /^v1\/governance\/bind-receipts$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/governance\/bind-receipts\/[^/]+$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },

  // Trust logs
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
    pathPattern: /^v1\/trust\/feedback$/,
    method: "POST",
    roles: ["operator", "admin"],
  },

  {
    pathPattern: /^v1\/trust\/stats$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    // WAT settings are governed via /v1/governance/policy (canonical source of truth).
    pathPattern: /^v1\/wat\/(?!settings$)[^/]+$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/wat\/events$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/wat\/issue-shadow$/,
    method: "POST",
    roles: ["operator", "admin"],
  },
  {
    pathPattern: /^v1\/wat\/validate-shadow$/,
    method: "POST",
    roles: ["operator", "admin"],
  },
  {
    pathPattern: /^v1\/wat\/revocation\/[^/]+$/,
    method: "POST",
    roles: ["operator", "admin"],
  },

  // Trust log chain (signed)
  {
    pathPattern: /^v1\/trustlog\/verify$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/trustlog\/export$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },

  // Compliance
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
  {
    pathPattern: /^v1\/compliance\/deployment-readiness$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },

  // System control (admin only for halt/resume, viewer+ for status)
  { pathPattern: /^v1\/system\/halt$/, method: "POST", roles: ["admin"] },
  { pathPattern: /^v1\/system\/resume$/, method: "POST", roles: ["admin"] },
  {
    pathPattern: /^v1\/system\/halt-status$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },

  // Metrics & events
  { pathPattern: /^v1\/metrics$/, method: "GET", roles: ["viewer", "operator", "admin"] },
  { pathPattern: /^v1\/events$/, method: "GET", roles: ["viewer", "operator", "admin"] },

  // Reports
  {
    pathPattern: /^v1\/report\/eu_ai_act\/[^/]+$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },
  {
    pathPattern: /^v1\/report\/governance$/,
    method: "GET",
    roles: ["viewer", "operator", "admin"],
  },

  // Memory
  {
    pathPattern: /^v1\/memory\/search$/,
    method: "POST",
    roles: ["operator", "admin"],
  },
  {
    pathPattern: /^v1\/memory\/erase$/,
    method: "POST",
    roles: ["admin"],
  },

  // Safety validation
  {
    pathPattern: /^v1\/fuji\/validate$/,
    method: "POST",
    roles: ["operator", "admin"],
  },

  // NOTE: The following backend endpoints are intentionally excluded from the BFF proxy
  // and must be accessed directly (with API key) or are not exposed to browser clients:
  //   - WS  /v1/ws/trustlog       (WebSocket; not supported by BFF HTTP proxy)
  //   - POST /v1/replay/{id}      (internal replay; requires HMAC signature)
  //   - POST /v1/decision/replay/{id} (v2 replay; internal use)
  //   - POST /v1/memory/put       (internal memory write; prefer memory_auto_put in /decide)
  //   - POST /v1/memory/get       (internal memory read; prefer /decide context)
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
