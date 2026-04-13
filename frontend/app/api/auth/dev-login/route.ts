import { NextResponse } from "next/server";

/**
 * Development-only convenience endpoint that sets the BFF session cookie
 * and redirects the browser to the Decision Console.
 *
 * How it works:
 *   GET /api/auth/dev-login
 *     → Sets __veritas_bff httpOnly cookie from VERITAS_BFF_SESSION_TOKEN
 *     → Redirects to /console (or ?redirect= target)
 *
 * Security:
 *   - Returns 403 in production runtime (VERITAS_ENV=prod|production
 *     or NODE_ENV=production).
 *   - Returns 503 when VERITAS_BFF_SESSION_TOKEN is not configured.
 *   - Never exposes the token value in response bodies.
 *
 * To remove: delete this file. No other files depend on it.
 */

const BFF_SESSION_COOKIE = "__veritas_bff";
const BFF_SESSION_TOKEN_ENV = "VERITAS_BFF_SESSION_TOKEN";

/** Returns true when the runtime is production. */
function isProduction(): boolean {
  const veritasEnv = (process.env.VERITAS_ENV ?? "").toLowerCase();
  const nodeEnv = (process.env.NODE_ENV ?? "").toLowerCase();
  return (
    veritasEnv === "prod" ||
    veritasEnv === "production" ||
    nodeEnv === "production"
  );
}

export async function GET(request: Request): Promise<Response> {
  // ── Guard: never run in production ──
  if (isProduction()) {
    return NextResponse.json(
      { error: "forbidden", detail: "Dev login is disabled in production." },
      { status: 403 },
    );
  }

  const sessionToken = (process.env[BFF_SESSION_TOKEN_ENV] ?? "").trim();
  if (!sessionToken) {
    return NextResponse.json(
      {
        error: "not_configured",
        detail:
          "VERITAS_BFF_SESSION_TOKEN is not set. " +
          "Add it to frontend/.env.development or your environment.",
      },
      { status: 503 },
    );
  }

  // ── Resolve redirect target ──
  const url = new URL(request.url);
  const redirectTarget = url.searchParams.get("redirect") ?? "/console";

  // Validate redirect is a safe relative path (no open-redirect).
  // Reject protocol-relative URLs (//evil.example) and non-relative paths.
  const safeRedirect =
    redirectTarget.startsWith("/") && !redirectTarget.startsWith("//")
      ? redirectTarget
      : "/console";

  const response = NextResponse.redirect(new URL(safeRedirect, url.origin));

  // ── Set the BFF session cookie ──
  response.cookies.set(BFF_SESSION_COOKIE, sessionToken, {
    httpOnly: true,
    secure: false, // localhost is HTTP; middleware handles HTTPS detection
    sameSite: "lax",
    path: "/api/veritas",
  });

  return response;
}
