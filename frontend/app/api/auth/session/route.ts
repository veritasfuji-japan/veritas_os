import { NextRequest, NextResponse } from "next/server";

import { authenticateRoleFromHeaders, parseAuthTokensConfig } from "../../veritas/[...path]/route-auth";

export async function GET(request: NextRequest): Promise<NextResponse> {
  const tokenRoleMap = parseAuthTokensConfig(process.env.VERITAS_BFF_AUTH_TOKENS_JSON);
  const authResult = authenticateRoleFromHeaders(request.headers, tokenRoleMap);

  if (authResult.errorResponse) {
    if (authResult.errorResponse.status === 401) {
      return NextResponse.json({ ok: false, error: "unauthorized" }, { status: 401 });
    }
    if (authResult.errorResponse.status === 503) {
      return NextResponse.json({ ok: false, error: "server_misconfigured" }, { status: 503 });
    }
    return NextResponse.json({ ok: false, error: "forbidden" }, { status: 403 });
  }

  return NextResponse.json({ ok: true, role: authResult.role }, { status: 200 });
}
