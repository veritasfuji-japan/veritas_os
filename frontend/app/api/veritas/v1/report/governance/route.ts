import { NextResponse } from "next/server";

import { resolveApiBaseUrl } from "../../../[...path]/route-config";

const GOVERNANCE_REPORT_PATH = "/v1/report/governance";
const E2E_SCENARIO_HEADER = "x-veritas-e2e-governance-scenario";
const E2E_SCENARIO_QUERY = "e2e_governance_scenario";

function resolveE2EScenarioPayload(request: Request): Record<string, unknown> | null {
  const scenarioFromQuery = new URL(request.url).searchParams.get(E2E_SCENARIO_QUERY)?.trim();
  const scenario = scenarioFromQuery || request.headers.get(E2E_SCENARIO_HEADER)?.trim();
  if (scenario === "main") {
    return {
      governance_layer_snapshot: {
        participation_state: "decision_shaping",
        preservation_state: "degrading",
        intervention_viability: "minimal",
        bind_outcome: "ESCALATED",
      },
    };
  }

  if (scenario === "fallback") {
    return {
      governance_layer_snapshot: {
        participation_state: "participatory",
        preservation_state: "open",
        intervention_viability: "high",
        bind_outcome: "BLOCKED",
      },
    };
  }

  return null;
}

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
export async function GET(request: Request): Promise<Response> {
  const e2ePayload = resolveE2EScenarioPayload(request);
  if (e2ePayload) {
    return NextResponse.json(e2ePayload, { status: 200 });
  }

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
