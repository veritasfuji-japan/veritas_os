import { NextResponse } from "next/server";

import { resolveApiBaseUrl } from "../../../[...path]/route-config";

const GOVERNANCE_REPORT_PATH = "/v1/report/governance";

function resolveApiKey(): string {
  return (process.env.VERITAS_API_KEY ?? "").trim();
}

function normalizeGovernanceReportPayload(payload: unknown): Record<string, unknown> | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }

  const source = payload as Record<string, unknown>;
  const governanceLayerSnapshot = source.governance_layer_snapshot;
  if (typeof governanceLayerSnapshot === "object" && governanceLayerSnapshot !== null) {
    return { governance_layer_snapshot: governanceLayerSnapshot };
  }

  const preBindGovernanceSnapshot = source.pre_bind_governance_snapshot;
  if (typeof preBindGovernanceSnapshot === "object" && preBindGovernanceSnapshot !== null) {
    return { pre_bind_governance_snapshot: preBindGovernanceSnapshot };
  }

  return null;
}

/**
 * Mission Control backend-fed governance feed endpoint.
 *
 * Main path fetches backend governance report and keeps payload vocabulary stable.
 */
export async function GET(): Promise<Response> {
  const apiBaseUrl = resolveApiBaseUrl();
  if (!apiBaseUrl) {
    return NextResponse.json({ error: "governance_feed_unavailable" }, { status: 503 });
  }

  const apiKey = resolveApiKey();
  if (!apiKey) {
    return NextResponse.json({ error: "governance_feed_unavailable" }, { status: 503 });
  }

  try {
    const upstreamResponse = await fetch(`${apiBaseUrl.replace(/\/$/, "")}${GOVERNANCE_REPORT_PATH}`, {
      method: "GET",
      headers: {
        "X-API-Key": apiKey,
      },
      cache: "no-store",
    });

    if (!upstreamResponse.ok) {
      return NextResponse.json({ error: "governance_feed_unavailable" }, { status: upstreamResponse.status });
    }

    const payload = normalizeGovernanceReportPayload((await upstreamResponse.json()) as unknown);
    if (!payload) {
      return NextResponse.json({ error: "invalid_governance_feed_payload" }, { status: 502 });
    }

    return NextResponse.json(payload, { status: 200 });
  } catch {
    return NextResponse.json({ error: "governance_feed_unavailable" }, { status: 503 });
  }
}
