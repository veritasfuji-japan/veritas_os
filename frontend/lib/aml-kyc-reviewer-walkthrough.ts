import { readFile } from "node:fs/promises";
import path from "node:path";

const SCENARIO_FILE_PATH = path.resolve(
  process.cwd(),
  "..",
  "veritas_os",
  "sample_data",
  "governance",
  "aml_kyc_regulated_action_path",
  "scenarios.json",
);

const REVIEWER_SCENARIO_NAME = "scenario_e_missing_authority";

/**
 * Build deterministic reviewer walkthrough payload for missing-authority behavior.
 */
export async function buildAmlKycReviewerWalkthroughPayload(): Promise<Record<string, unknown>> {
  const raw = await readFile(SCENARIO_FILE_PATH, "utf-8");
  const parsed = JSON.parse(raw) as { scenarios?: Array<Record<string, unknown>> };
  const scenarios = Array.isArray(parsed.scenarios) ? parsed.scenarios : [];
  const scenario = scenarios.find((item) => item.scenario_name === REVIEWER_SCENARIO_NAME);
  if (!scenario) {
    throw new Error("missing reviewer walkthrough scenario");
  }

  const riskFlags = typeof scenario.risk_flags === "object" && scenario.risk_flags !== null ? scenario.risk_flags : {};
  const requestedScope = Array.isArray(scenario.requested_scope) && scenario.requested_scope.length > 0
    ? String(scenario.requested_scope[0])
    : "create_internal_risk_escalation";

  return {
    governance_layer_snapshot: {
      demo_scenario: "aml_kyc_reviewer_walkthrough",
      source_state: "fixture",
      scenario_id: REVIEWER_SCENARIO_NAME,
      scenario_name: REVIEWER_SCENARIO_NAME,
      scenario_title: "AML/KYC Missing Authority Evidence Walkthrough",
      decision_id: "fixture.decision.aml_kyc.scenario_e_missing_authority",
      execution_intent_id: "fixture.execution_intent.aml_kyc.scenario_e_missing_authority",
      bind_receipt_id: "fixture.bind_receipt.aml_kyc.scenario_e_missing_authority",
      action_class: "aml_kyc_customer_risk_escalation",
      requested_action: requestedScope,
      requested_scope: requestedScope,
      customer_risk_context: {
        risk_score: scenario.risk_score,
        risk_flags: riskFlags,
        actor_identity: scenario.actor_identity,
      },
      authority_evidence_status: "missing",
      authority_check_result: "fail_closed_missing_authority_evidence",
      bind_outcome: "block",
      bind_reason_code: "AUTHORITY_MISSING",
      bind_failure_reason: "authority evidence missing",
      bind_summary: "missing authority evidence triggers fail-closed block before commit",
      audit_trace: [
        { event: "decision_created", source_state: "fixture" },
        { event: "execution_intent_requested", source_state: "fixture" },
        { event: "authority_evidence_validation_failed", source_state: "fixture" },
        { event: "bind_boundary_blocked", source_state: "fixture" },
        { event: "bind_receipt_recorded", source_state: "fixture" },
      ],
      evidence_bundle_summary: "fixture-only AML/KYC packet: policy snapshot, risk flags, and missing authority evidence marker; no live customer or sanctions data.",
      reviewer_expected_steps: [
        "Open Mission Control reviewer panel",
        "Confirm Authority Evidence is missing",
        "Confirm bind outcome is block before commit",
        "Open safe audit link and inspect trace ordering",
      ],
    },
  };
}
