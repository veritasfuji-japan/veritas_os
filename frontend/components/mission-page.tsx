"use client";

import { Card } from "@veritas/design-system";
import Link from "next/link";
import { CriticalRail } from "./critical-rail";
import { GlobalHealthSummary } from "./global-health-summary";
import { OpsPriorityCard } from "./ops-priority-card";
import { SourceStateBadge } from "./source-state-badge";
import { useI18n } from "./i18n-provider";
import { buildAuditArtifactHref, normalizeSafeInternalHref } from "../lib/governance-link-utils";
import {
  resolveDemoSourceState,
  resolveGovernanceSourceState,
  resolveOperationalSourceState,
  resolveStaticFixtureSourceState,
  resolveUnavailableSourceState,
} from "../lib/source-state-utils";
import {
  type CriticalRailMetric,
  type DecisionEvidenceRouteModel,
  type GlobalHealthSummaryModel,
  type GovernanceApprovalModel,
  type MissionUiState,
  type OpsPriorityItem,
  type PreBindGovernanceSnapshot,
  type ReplayDiffInsightModel,
  type TrustChainIntegrityModel,
  PRE_BIND_GOVERNANCE_VOCABULARY_LABELS,
} from "./dashboard-types";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
  governanceLayerSnapshot?: PreBindGovernanceSnapshot;
}

const AUDIT_ROUTE_AVAILABLE = true;

const CRITICAL_RAIL_ITEMS: CriticalRailMetric[] = [
  {
    key: "fuji-reject",
    label: "FUJI reject",
    severity: "critical",
    currentValue: "+12 / 15m",
    baselineDelta: "+140%",
    owner: "Fuji",
    lastUpdated: "06:12",
    openIncidents: 4,
    href: "/console",
  },
  {
    key: "replay-mismatch",
    label: "Replay mismatch",
    severity: "critical",
    currentValue: "3 active",
    baselineDelta: "+2.0",
    owner: "Kernel",
    lastUpdated: "06:10",
    openIncidents: 3,
    href: "/audit",
  },
  {
    key: "policy-update",
    label: "policy update pending",
    severity: "degraded",
    currentValue: "pending sign-off",
    baselineDelta: "+1 pending",
    owner: "Governance",
    lastUpdated: "06:08",
    openIncidents: 1,
    href: "/governance",
  },
  {
    key: "broken-chain",
    label: "broken hash chain",
    severity: "critical",
    currentValue: "2 segments",
    baselineDelta: "+2",
    owner: "TrustLog",
    lastUpdated: "06:09",
    openIncidents: 2,
    href: "/audit",
  },
  {
    key: "risk-burst",
    label: "risk burst",
    severity: "critical",
    currentValue: "p99 +38%",
    baselineDelta: "+31%",
    owner: "Risk Ops",
    lastUpdated: "06:11",
    openIncidents: 5,
    href: "/risk",
  },
];

const OPS_PRIORITY_ITEMS: OpsPriorityItem[] = [
  {
    key: "priority-1",
    titleJa: "#1 最優先: FUJI拒否トリアージ",
    titleEn: "#1 Highest risk: FUJI reject triage",
    owner: "Planner + Fuji",
    whyNowJa: "policy.v44 適用直後に拒否率が急増。誤拒否と真性危険の分離が必要。",
    whyNowEn: "Reject rate surged after policy.v44 rollout. Separate false rejects from real risks now.",
    impactWindowJa: "次の30分で手動審査キューがSLOを超過する見込み。",
    impactWindowEn: "Manual review queue is expected to exceed SLO within 30 minutes.",
    ctaJa: "Decision で triage",
    ctaEn: "Triage in Decision",
    href: "/console",
  },
  {
    key: "priority-2",
    titleJa: "#2 監査連鎖の復旧",
    titleEn: "#2 Restore audit chain continuity",
    owner: "Kernel + TrustLog",
    whyNowJa: "replay mismatch と broken hash chain が同時発生。証跡の連続性に影響。",
    whyNowEn: "Replay mismatch and broken hash chain are co-occurring, threatening trace continuity.",
    impactWindowJa: "直近24hの監査レポート確定前に連鎖復旧が必要。",
    impactWindowEn: "Chain recovery is needed before finalizing the last 24h audit report.",
    ctaJa: "TrustLog で確認",
    ctaEn: "Investigate in TrustLog",
    href: "/audit",
  },
  {
    key: "priority-3",
    titleJa: "#3 Policy保留の解消",
    titleEn: "#3 Clear pending policy updates",
    owner: "Governance",
    whyNowJa: "policy update pending が risk burst と連動し、設定乖離が拡大中。",
    whyNowEn: "Pending policy updates are coupling with risk burst and increasing config drift.",
    impactWindowJa: "次のリリース判定会議までに sign-off 完了が必要。",
    impactWindowEn: "Sign-off must be completed before the next release decision meeting.",
    ctaJa: "Governance で承認",
    ctaEn: "Approve in Governance",
    href: "/governance",
  },
];

const GLOBAL_HEALTH_SUMMARY: GlobalHealthSummaryModel = {
  band: "critical",
  todayChanges: [
    "FUJI reject rate +140% vs baseline",
    "Replay mismatch incidents: 3 active",
    "Policy update pending sign-off: 1",
  ],
  incidents24h: "critical 6 / degraded 11 / resolved 19",
  policyDrift: "1 pending update with elevated blast radius.",
  trustDegradation: "Hash-chain discontinuity found in 2 segments.",
  decisionAnomalies: "Reject spike concentrated on policy.v44 path.",
};

const TRUST_CHAIN_INTEGRITY: TrustChainIntegrityModel = {
  verificationStatus: "broken",
  continuityRatio: 0.92,
  brokenSegments: 2,
  lastVerifiedAt: "06:09",
  verifier: "TrustLog hash daemon",
  blockedReports: 1,
};

const REPLAY_DIFF_INSIGHT: ReplayDiffInsightModel = {
  status: "critical",
  changedFields: ["decision", "fuji", "value_scores"],
  safetySensitiveFields: ["decision", "fuji"],
  operatorActionJa: "Decision と TrustLog を並べて確認し、critical フィールド差分を先に再判定する。",
  operatorActionEn: "Cross-check Decision and TrustLog, then re-adjudicate critical field differences first.",
};

const GOVERNANCE_APPROVAL: GovernanceApprovalModel = {
  pendingVersion: "policy.v44",
  status: "blocked",
  requiredApprovers: ["risk-owner", "safety-officer", "governance-admin"],
  missingApprovers: ["safety-officer"],
  policyRiskDelta: "+0.18 risk score in high-risk route",
};

const DECISION_EVIDENCE_ROUTE: DecisionEvidenceRouteModel = {
  riskSignal: "risk burst p99 +38%",
  decisionTarget: "Decision Console triage queue",
  evidenceAnchor: "TrustLog replay verification set #2026-03-26-0610",
  reportingTarget: "24h incident report bundle (audit + governance)",
};

const POLICY_DIFF_IMPACT_PREVIEW = {
  status: "connected",
  previewTarget: "/governance",
  summary: "Policy diff/impact preview is now linked to Mission Control action flow.",
};

const HEALTH_SECURITY_POSTURE = {
  encryptionAlgorithm: "AES-256-GCM",
  authenticationMode: "requested=redis / effective=memory (fail-closed)",
  directFujiApi: "disabled",
};

/**
 * MissionPage renders the operational command-center view.
 *
 * The page surfaces the highest-risk anomaly first, then gives direct
 * intervention cards so operators can transition from monitoring to action.
 */
export function MissionPage({ title, subtitle, chips, governanceLayerSnapshot }: MissionPageProps): JSX.Element {
  const { t } = useI18n();
  const uiState: MissionUiState = TRUST_CHAIN_INTEGRITY.verificationStatus === "broken" ? "degraded" : "operational";
  const governanceSnapshot = governanceLayerSnapshot;
  const stringifyValue = (value: unknown): string => {
    if (value === null || value === undefined) {
      return "not available";
    }
    if (typeof value === "string") {
      return value;
    }
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  };
  const resolvePreBindSourceTone = (source?: string): string => {
    if (source === "trustlog_matching_decision" || source === "trustlog_matching_request" || source === "trustlog_matching_execution_intent") {
      return "matched";
    }
    if (source === "trustlog_recent_decision" || source === "latest_bind_receipt") {
      return "fallback";
    }
    if (source === "pre_bind_artifact_retrieval_failed" || source === "malformed_pre_bind_artifact") {
      return "degraded";
    }
    if (source === "none") {
      return "unavailable";
    }
    return "unknown";
  };

  const relevantUiHref = normalizeSafeInternalHref(governanceSnapshot?.relevant_ui_href);
  const bindReceiptAuditHref = AUDIT_ROUTE_AVAILABLE
    ? buildAuditArtifactHref("bind_receipt_id", governanceSnapshot?.bind_receipt_id)
    : null;
  const decisionAuditHref = AUDIT_ROUTE_AVAILABLE
    ? buildAuditArtifactHref("decision_id", governanceSnapshot?.decision_id)
    : null;
  const executionIntentAuditHref = AUDIT_ROUTE_AVAILABLE
    ? buildAuditArtifactHref("execution_intent_id", governanceSnapshot?.execution_intent_id)
    : null;

  const hasPreBindGovernance = Boolean(
    governanceSnapshot?.participation_state ||
      governanceSnapshot?.preservation_state ||
      governanceSnapshot?.intervention_viability,
  );
  const phaseSnapshots = Array.isArray(governanceSnapshot?.phase_snapshots)
    ? governanceSnapshot.phase_snapshots
    : [];
  const hasPreBoundaryCollapseDemo = governanceSnapshot?.demo_scenario === "pre_boundary_collapse" && phaseSnapshots.length > 0;
  const abcdMinimalValidationCase = governanceSnapshot?.trajectory_shaping_lineage?.abcd_minimal_validation_case;
  const dynamicConditionsValidationCase = governanceSnapshot?.trajectory_shaping_lineage?.dynamic_conditions_validation_case;
  const irreversibilityHorizon = dynamicConditionsValidationCase?.irreversibility_horizon;
  const hasAmlKycReviewerWalkthrough = governanceSnapshot?.demo_scenario === "aml_kyc_reviewer_walkthrough";

  const governanceObservation = governanceSnapshot?.governance_observation;
  const hasGovernanceObservation = governanceObservation != null;
  const actionDrilldownHref = bindReceiptAuditHref ?? decisionAuditHref ?? executionIntentAuditHref;
  const renderObservationValue = (value: unknown): string => {
    if (value === null || value === undefined) {
      return "not available";
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
    return stringifyValue(value);
  };

  const statusMessage = {
    loading: t("データ同期中: 信頼状態の確定前です。", "Syncing data: trust state not yet confirmed."),
    empty: t("監視データなし: オペレーター確認が必要です。", "No monitoring data: operator verification required."),
    degraded: t("degraded: 監査連鎖が断続し、レポート確定を一部停止しています。", "Degraded: audit-chain continuity is broken and report finalization is partially blocked."),
    operational: t("operational: 信頼連鎖は検証済みです。", "Operational: trust chain is verified."),
  }[uiState];
  const governanceState = resolveGovernanceSourceState(governanceSnapshot?.pre_bind_source, governanceSnapshot?.demo_scenario);
  const governanceReason = governanceSnapshot?.demo_scenario
    ? "demo_scenario"
    : governanceState === "unavailable"
      ? "missing_payload"
      : "trustlog_matching_decision";
  const globalHealthSource = resolveStaticFixtureSourceState(GLOBAL_HEALTH_SUMMARY);
  const criticalRailSource = resolveStaticFixtureSourceState(CRITICAL_RAIL_ITEMS);
  const systemStateSource = resolveStaticFixtureSourceState(statusMessage);
  const healthPostureSource = resolveStaticFixtureSourceState(HEALTH_SECURITY_POSTURE);
  const trustChainSource = resolveStaticFixtureSourceState(TRUST_CHAIN_INTEGRITY);
  const approvalRiskSource = resolveStaticFixtureSourceState(GOVERNANCE_APPROVAL);
  const replayDiffSource = resolveStaticFixtureSourceState(REPLAY_DIFF_INSIGHT);
  const evidenceRouteSource = resolveDemoSourceState(DECISION_EVIDENCE_ROUTE, true);
  const policyPreviewSource = resolveDemoSourceState(POLICY_DIFF_IMPACT_PREVIEW, true);
  const amlDrilldownSource = actionDrilldownHref
    ? resolveOperationalSourceState(actionDrilldownHref)
    : resolveUnavailableSourceState("missing_payload");

  return (
    <div className="space-y-6">
      <Card title={title} titleSize="lg" variant="glass" description={subtitle} className="border-primary/20" accent="primary">
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <span key={chip} className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/8 px-3 py-1 text-xs font-medium text-primary">
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              {chip}
            </span>
          ))}
        </div>
      </Card>

      <section aria-label="mission control provenance summary" className="rounded-xl border border-border/70 bg-muted/10 p-4 text-xs">
        <p className="font-semibold">Mission Control provenance: mixed</p>
        <p className="text-muted-foreground">live: governance artifacts / AML-KYC drilldown · fixture: critical rail, trust chain · demo: evidence route, policy preview · unavailable: missing drilldown ids</p>
      </section>
      <GlobalHealthSummary summary={GLOBAL_HEALTH_SUMMARY} sourceState={globalHealthSource.state} sourceStateReason={globalHealthSource.reason} />
      <CriticalRail items={CRITICAL_RAIL_ITEMS} sourceState={criticalRailSource.state} sourceStateReason={criticalRailSource.reason} />
      <section aria-label="mission control state" className="rounded-xl border border-border/70 bg-background/70 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">System state <SourceStateBadge state={systemStateSource.state} reason={systemStateSource.reason} compact className="ml-2" /></p>
        <p className={["mt-1 text-sm font-semibold", uiState === "degraded" ? "text-danger" : "text-foreground"].join(" ")}>{statusMessage}</p>
      </section>

      {hasPreBindGovernance ? (
        <section aria-label="governance layer timeline" className="rounded-xl border border-info/40 bg-info/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-info">{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.heading}<SourceStateBadge state={governanceState} reason={governanceReason} compact className="ml-2" /></p>
          <ol className="mt-2 list-decimal space-y-1 pl-4 text-xs">
            <li>
              <span className="font-semibold">{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.participation_state}:</span>{" "}
              <span className="font-mono">{governanceSnapshot?.participation_state ?? PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.unavailable}</span>
            </li>
            <li>
              <span className="font-semibold">{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.preservation_state}:</span>{" "}
              <span className="font-mono">{governanceSnapshot?.preservation_state ?? PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.unavailable}</span>
              {governanceSnapshot?.intervention_viability ? (
                <span className="text-muted-foreground"> ({PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.intervention_viability}: <span className="font-mono">{governanceSnapshot?.intervention_viability}</span>)</span>
              ) : null}
            </li>
            {governanceSnapshot?.bind_outcome ? (
              <li>
                <span className="font-semibold">{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.bind_outcome}:</span>{" "}
                <span className="font-mono">{governanceSnapshot?.bind_outcome}</span>
              </li>
            ) : null}
          </ol>
          {governanceSnapshot?.concise_rationale ? (
            <p className="mt-2 text-xs text-muted-foreground">
              <span className="font-semibold">{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.concise_rationale}:</span> {governanceSnapshot?.concise_rationale}
            </p>
          ) : null}
        </section>
      ) : null}

      {hasAmlKycReviewerWalkthrough ? (
        <section aria-label="aml kyc reviewer walkthrough" className="rounded-xl border border-warning/40 bg-warning/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-warning">AML/KYC Reviewer Walkthrough <SourceStateBadge state={resolveGovernanceSourceState("none", governanceSnapshot?.demo_scenario)} reason="demo_scenario" compact className="ml-2" /></p>
          <p className="mt-1 text-xs font-semibold">Authority Evidence: <span className="text-warning">missing</span> · Bind result: <span className="text-danger">block</span></p>
          <ul className="mt-2 space-y-1 text-xs">
            <li>scenario_id: <span className="font-mono">{stringifyValue(governanceSnapshot?.scenario_id)}</span></li>
            <li>scenario_name: <span className="font-mono">{stringifyValue(governanceSnapshot?.scenario_name)}</span></li>
            <li>action_class: <span className="font-mono">{stringifyValue(governanceSnapshot?.action_class)}</span></li>
            <li>requested_action / requested_scope: <span className="font-mono">{stringifyValue(governanceSnapshot?.requested_action)} / {stringifyValue(governanceSnapshot?.requested_scope)}</span></li>
            <li>customer_risk_context: <span className="font-mono">{stringifyValue(governanceSnapshot?.customer_risk_context)}</span></li>
            <li>bind_reason_code: <span className="font-mono">{stringifyValue(governanceSnapshot?.bind_reason_code)}</span></li>
            <li>bind_failure_reason: <span className="font-mono">{stringifyValue(governanceSnapshot?.bind_failure_reason)}</span></li>
            <li>decision_id: {decisionAuditHref ? <Link className="underline font-mono" href={decisionAuditHref}>{governanceSnapshot?.decision_id}</Link> : <span className="font-mono">unavailable</span>}</li>
            <li>execution_intent_id: {executionIntentAuditHref ? <Link className="underline font-mono" href={executionIntentAuditHref}>{governanceSnapshot?.execution_intent_id}</Link> : <span className="font-mono">unavailable</span>}</li>
            <li>bind_receipt_id: {bindReceiptAuditHref ? <Link className="underline font-mono" href={bindReceiptAuditHref}>{governanceSnapshot?.bind_receipt_id}</Link> : <span className="font-mono">unavailable</span>}</li>
            <li>audit path: {actionDrilldownHref ? <Link className="underline" href={actionDrilldownHref}>open audit path</Link> : <span className="font-mono">unavailable</span>}</li>
            <li>evidence_bundle_summary: <span className="font-mono">{stringifyValue(governanceSnapshot?.evidence_bundle_summary)}</span></li>
            <li>reviewer_expected_steps: <span className="font-mono">{stringifyValue(governanceSnapshot?.reviewer_expected_steps)}</span></li>
          </ul>
        </section>
      ) : null}

      {hasPreBoundaryCollapseDemo ? (
        <section aria-label="pre-boundary collapse demo walkthrough" className="rounded-xl border border-warning/40 bg-warning/5 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-warning">Pre-Boundary Collapse Demo · 4 phase walkthrough</p>
          <p className="mt-1 text-xs text-muted-foreground">formal options remain, effective optionality collapses before bind.</p>
          <p className="mt-1 text-xs font-medium">formally valid, structurally collapsed</p>
          <ol className="mt-3 space-y-3">
            {phaseSnapshots.map((phase, index) => {
              const phaseRecord = phase as Record<string, unknown>;
              const phaseLabel = typeof phaseRecord.phase_label === "string" ? phaseRecord.phase_label : `Phase ${index + 1}`;
              return (
                <li key={String(phaseRecord.phase_id ?? index)} className="rounded-md border border-border/60 bg-background/70 p-3 text-xs">
                  <p className="font-semibold">{phaseLabel}</p>
                  <p>{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.participation_state}: <span className="font-mono">{stringifyValue(phaseRecord.participation_state)}</span></p>
                  <p>{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.preservation_state}: <span className="font-mono">{stringifyValue(phaseRecord.preservation_state)}</span></p>
                  <p>{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.intervention_viability}: <span className="font-mono">{stringifyValue(phaseRecord.intervention_viability)}</span></p>
                  <p>{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.bind_outcome}: <span className="font-mono">{stringifyValue(phaseRecord.bind_outcome)}</span></p>
                  <p>{PRE_BIND_GOVERNANCE_VOCABULARY_LABELS.concise_rationale}: <span className="text-muted-foreground">{stringifyValue(phaseRecord.concise_rationale)}</span></p>
                  <p>effective optionality: <span className="font-mono">{stringifyValue(phaseRecord.effective_optionality)}</span></p>
                  <p>option exposure summary: <span className="font-mono">{stringifyValue(phaseRecord.option_exposure_summary)}</span></p>
                  <p>reinforcement asymmetry summary: <span className="font-mono">{stringifyValue(phaseRecord.reinforcement_asymmetry_summary)}</span></p>
                  <p>lineage evidence summary: <span className="font-mono">{stringifyValue(phaseRecord.lineage_evidence)}</span></p>
                </li>
              );
            })}
          </ol>
          {governanceSnapshot?.trajectory_shaping_lineage ? (
            <div
              aria-label="trajectory shaping lineage"
              data-testid="trajectory-shaping-lineage-panel"
              className="mt-3 rounded-md border border-border/60 bg-background/70 p-3 text-xs"
            >
              <p className="font-semibold">Trajectory Shaping Lineage v0</p>
              <p className="text-muted-foreground">Decision-space transformation before bind</p>
              <ul className="mt-2 space-y-1">
                <li>initial option space: <span className="font-mono">{stringifyValue(governanceSnapshot.trajectory_shaping_lineage.initial_option_space.options)}</span></li>
                <li>first detectable asymmetry: <span className="font-mono">{stringifyValue(governanceSnapshot.trajectory_shaping_lineage.transition_points.first_detectable_asymmetry_phase)}</span></li>
                <li>divergence contraction: <span className="font-mono">{stringifyValue(governanceSnapshot.trajectory_shaping_lineage.transition_points.divergence_contraction_phase)}</span></li>
                <li>intervention viability loss: <span className="font-mono">{stringifyValue(governanceSnapshot.trajectory_shaping_lineage.transition_points.intervention_viability_loss_phase)}</span></li>
                <li>bind evaluation: <span className="font-mono">{stringifyValue(governanceSnapshot.trajectory_shaping_lineage.transition_points.bind_evaluation_phase)}</span></li>
                <li>summary: <span className="text-muted-foreground">{stringifyValue(governanceSnapshot.trajectory_shaping_lineage.summary.concise)}</span></li>
              </ul>
              {abcdMinimalValidationCase ? (
                <div
                  aria-label="A/B/C/D minimal validation case"
                  className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3"
                >
                  <p className="font-semibold">A/B/C/D Minimal Validation Case</p>
                  <p className="text-muted-foreground">Testing separation between preservation, intervention viability, and formal bind admissibility</p>
                  <ul className="mt-2 space-y-1">
                    <li>Options: <span className="font-mono">{abcdMinimalValidationCase.options.join("/")}</span></li>
                    <li>first detectable asymmetry: <span className="font-mono">{stringifyValue(abcdMinimalValidationCase.separation_points.first_detectable_asymmetry_phase)}</span></li>
                    <li>divergence contraction: <span className="font-mono">{stringifyValue(abcdMinimalValidationCase.separation_points.divergence_contraction_phase)}</span></li>
                    <li>intervention viability loss: <span className="font-mono">{stringifyValue(abcdMinimalValidationCase.separation_points.intervention_viability_loss_phase)}</span></li>
                    <li>formal admissibility: <span className="font-mono">{stringifyValue(abcdMinimalValidationCase.separation_points.formal_admissibility_phase)}</span></li>
                    <li>summary: <span className="text-muted-foreground">{stringifyValue(abcdMinimalValidationCase.summary.concise)}</span></li>
                  </ul>
                </div>
              ) : null}
              {dynamicConditionsValidationCase ? (
                <div
                  aria-label="Dynamic Conditions Validation v0"
                  className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3"
                >
                  <p className="font-semibold">Dynamic Conditions Validation v0</p>
                  <p className="text-muted-foreground">Testing separation stability under reinforcement, exposure asymmetry, time pressure, and adaptive behavior</p>
                  <ul className="mt-2 space-y-1">
                    <li>Base case: <span className="font-mono">A/B/C/D Minimal Validation Case</span></li>
                    <li>dynamic factors:</li>
                    <li className="ml-3">reinforcement</li>
                    <li className="ml-3">exposure asymmetry</li>
                    <li className="ml-3">time pressure</li>
                    <li className="ml-3">adaptive behavior</li>
                    <li>first dynamic asymmetry: <span className="font-mono">{stringifyValue(dynamicConditionsValidationCase.separation_points.first_dynamic_asymmetry_phase)}</span></li>
                    <li>intervention window compression: <span className="font-mono">{stringifyValue(dynamicConditionsValidationCase.separation_points.intervention_window_compression_phase)}</span></li>
                    <li>adaptive narrowing: <span className="font-mono">{stringifyValue(dynamicConditionsValidationCase.separation_points.adaptive_narrowing_phase)}</span></li>
                    <li>intervention viability loss: <span className="font-mono">{stringifyValue(dynamicConditionsValidationCase.separation_points.intervention_viability_loss_phase)}</span></li>
                    <li>formal admissibility: <span className="font-mono">{stringifyValue(dynamicConditionsValidationCase.separation_points.formal_admissibility_phase)}</span></li>
                    <li>summary: <span className="text-muted-foreground">{stringifyValue(dynamicConditionsValidationCase.summary.concise)}</span></li>
                  </ul>
                  {irreversibilityHorizon ? (
                    <div
                      aria-label="Irreversibility Horizon v0"
                      className="mt-3 rounded-md border border-border/60 bg-background/60 p-3"
                    >
                      <p className="font-semibold">Irreversibility Horizon v0</p>
                      <p className="text-muted-foreground">Marking the last meaningful intervention point before operational irreversibility stabilizes</p>
                      <ul className="mt-2 space-y-1">
                        <li>first structural degradation signal: <span className="font-mono">{stringifyValue(irreversibilityHorizon.markers.first_structural_degradation_signal_phase)}</span></li>
                        <li>early warning: <span className="font-mono">{stringifyValue(irreversibilityHorizon.markers.early_warning_phase)}</span></li>
                        <li>last meaningful intervention: <span className="font-mono">{stringifyValue(irreversibilityHorizon.markers.last_meaningful_intervention_phase)}</span></li>
                        <li>irreversibility horizon: <span className="font-mono">{stringifyValue(irreversibilityHorizon.markers.irreversibility_horizon_phase)}</span></li>
                        <li>bind after horizon: <span className="font-mono">{stringifyValue(irreversibilityHorizon.markers.bind_after_horizon_phase)}</span></li>
                        <li>summary: <span className="text-muted-foreground">{stringifyValue(irreversibilityHorizon.summary.concise)}</span></li>
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      ) : null}

      <section aria-label="governance artifact details" className="rounded-xl border border-border/70 bg-background/70 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Governance artifacts<SourceStateBadge state={governanceState} reason={governanceReason} compact className="ml-2" /></p>
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          <div className="rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
            <p className="font-semibold">Pre-bind source</p>
            <p className="mt-1 font-mono">{governanceSnapshot?.pre_bind_source ?? "unknown"}</p>
            <p className="text-muted-foreground">classification: {resolvePreBindSourceTone(governanceSnapshot?.pre_bind_source)}</p>
          </div>
          <div className="rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
            <p className="font-semibold">Bind reason</p>
            <p>code: <span className="font-mono">{governanceSnapshot?.bind_reason_code ?? "not available"}</span></p>
            <p>failure: <span className="font-mono">{governanceSnapshot?.bind_failure_reason ?? "not available"}</span></p>
            <p>category: <span className="font-mono">{governanceSnapshot?.failure_category ?? "not available"}</span></p>
            <p>rollback: <span className="font-mono">{governanceSnapshot?.rollback_status ?? "not available"}</span></p>
            <p>retry_safety: <span className="font-mono">{governanceSnapshot?.retry_safety ?? "not available"}</span></p>
          </div>
        </div>
        <details className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
          <summary className="cursor-pointer font-semibold">Pre-bind summaries</summary>
          <div className="mt-2 space-y-2">
            <div>
              <p className="font-semibold">Detection summary</p>
              {governanceSnapshot?.pre_bind_detection_summary == null ? <p>No pre-bind summary available</p> : <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot.pre_bind_detection_summary)}</pre>}
            </div>
            <div>
              <p className="font-semibold">Preservation summary</p>
              {governanceSnapshot?.pre_bind_preservation_summary == null ? <p>No pre-bind summary available</p> : <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot.pre_bind_preservation_summary)}</pre>}
            </div>
            {governanceSnapshot?.bind_summary == null ? null : (
              <div>
                <p className="font-semibold">Bind summary</p>
                <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot.bind_summary)}</pre>
              </div>
            )}
          </div>
        </details>
        {(governanceSnapshot?.pre_bind_detection_detail != null || governanceSnapshot?.pre_bind_preservation_detail != null) ? (
          <details className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
            <summary className="cursor-pointer font-semibold">Pre-bind details</summary>
            {governanceSnapshot?.pre_bind_detection_detail != null ? <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot.pre_bind_detection_detail)}</pre> : null}
            {governanceSnapshot?.pre_bind_preservation_detail != null ? <pre className="mt-2 overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot.pre_bind_preservation_detail)}</pre> : null}
          </details>
        ) : null}
        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
            <p className="font-semibold">Target metadata</p>
            <p>label: <span className="font-mono">{governanceSnapshot?.target_label ?? "not available"}</span></p>
            <p>path: <span className="font-mono">{governanceSnapshot?.target_path ?? "not available"}</span></p>
            <p>type: <span className="font-mono">{governanceSnapshot?.target_type ?? "not available"}</span></p>
            <p>path_type: <span className="font-mono">{governanceSnapshot?.target_path_type ?? "not available"}</span></p>
            <p>operator_surface: <span className="font-mono">{governanceSnapshot?.operator_surface ?? "not available"}</span></p>
            {relevantUiHref ? (
              <p>
                relevant_ui_href: <Link className="underline" href={relevantUiHref}>{relevantUiHref}</Link>
              </p>
            ) : governanceSnapshot?.relevant_ui_href != null ? (
              <p>
                relevant_ui_href: <span className="font-mono">{stringifyValue(governanceSnapshot.relevant_ui_href)}</span>{" "}
                <span className="text-muted-foreground">unsafe or external link not rendered</span>
              </p>
            ) : <p>relevant_ui_href: <span className="font-mono">not available</span></p>}
          </div>
          <div className="rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
            <p className="font-semibold">Check results</p>
            <p>authority_check_result</p>
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot?.authority_check_result)}</pre>
            <p>constraint_check_result</p>
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot?.constraint_check_result)}</pre>
            <p>drift_check_result</p>
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot?.drift_check_result)}</pre>
            <p>risk_check_result</p>
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono">{stringifyValue(governanceSnapshot?.risk_check_result)}</pre>
          </div>
        </div>
        {hasGovernanceObservation ? (
          <div className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
            <p className="font-semibold">Governance observation</p>
            <p className="mt-1 text-muted-foreground">Observation fields received from payload (read-only; runtime behavior unchanged).</p>
            <dl className="mt-2 grid grid-cols-[max-content_1fr] gap-x-3 gap-y-1">
              <dt>policy_mode</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.policy_mode)}</dd>
              <dt>environment</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.environment)}</dd>
              <dt>would_have_blocked</dt>
              <dd className={governanceObservation.would_have_blocked ? "font-mono font-semibold text-warning" : "font-mono"}>
                {renderObservationValue(governanceObservation.would_have_blocked)}
              </dd>
              <dt>would_have_blocked_reason</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.would_have_blocked_reason)}</dd>
              <dt>effective_outcome</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.effective_outcome)}</dd>
              <dt>observed_outcome</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.observed_outcome)}</dd>
              <dt>operator_warning</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.operator_warning)}</dd>
              <dt>audit_required</dt>
              <dd className="font-mono">{renderObservationValue(governanceObservation.audit_required)}</dd>
            </dl>
          </div>
        ) : null}

        <div className="mt-3 rounded-md border border-border/60 bg-muted/10 p-3 text-xs">
          <p className="font-semibold">Operator actions</p>
          <ul className="mt-2 space-y-1">
            <li>
              Open target surface:{" "}
              {relevantUiHref ? <Link className="underline" href={relevantUiHref}>{relevantUiHref}</Link> : <span className="font-mono">not available</span>}
            </li>
            <li>
              Review bind receipt:{" "}
              {bindReceiptAuditHref ? <Link className="underline font-mono" href={bindReceiptAuditHref}>{governanceSnapshot?.bind_receipt_id}</Link> : (
                <>
                  <span className="font-mono">{governanceSnapshot?.bind_receipt_id ?? "not available"}</span>{" "}
                  {governanceSnapshot?.bind_receipt_id ? <span className="text-muted-foreground">(route unavailable)</span> : null}
                </>
              )}
            </li>
            <li>
              View decision artifact:{" "}
              {decisionAuditHref ? <Link className="underline font-mono" href={decisionAuditHref}>{governanceSnapshot?.decision_id}</Link> : (
                <>
                  <span className="font-mono">{governanceSnapshot?.decision_id ?? "not available"}</span>{" "}
                  {governanceSnapshot?.decision_id ? <span className="text-muted-foreground">(route unavailable)</span> : null}
                </>
              )}
            </li>
            <li>
              View execution intent:{" "}
              {executionIntentAuditHref ? <Link className="underline font-mono" href={executionIntentAuditHref}>{governanceSnapshot?.execution_intent_id}</Link> : (
                <>
                  <span className="font-mono">{governanceSnapshot?.execution_intent_id ?? "not available"}</span>{" "}
                  {governanceSnapshot?.execution_intent_id ? <span className="text-muted-foreground">(route unavailable)</span> : null}
                </>
              )}
            </li>
            <li>
              View pre-bind source: <span className="font-mono">{governanceSnapshot?.pre_bind_source ?? "unknown"}</span>{" "}
              <span className="text-muted-foreground">(route unavailable)</span>
            </li>
            <li>
              AML/KYC evidence drilldown <SourceStateBadge state={amlDrilldownSource.state} reason={amlDrilldownSource.reason} compact className="ml-2" />: {actionDrilldownHref ? <Link className="underline" href={actionDrilldownHref}>open audit path</Link> : <span className="font-mono">unavailable</span>}
            </li>
            {governanceSnapshot?.bind_reason_code === "AUTHORITY_MISSING" ? (
              <li>Authority evidence status: <span className="text-warning">missing (bind blocked)</span></li>
            ) : null}
          </ul>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2" aria-label="trust and governance highlights">
        <Card title="Trust Chain Integrity" titleSize="sm" variant="elevated" accent="danger" className="border-danger/40">
          <SourceStateBadge state={trustChainSource.state} reason={trustChainSource.reason} compact />
          <div className="space-y-1 text-xs">
            <p>Verification: <span className="font-semibold text-danger">{TRUST_CHAIN_INTEGRITY.verificationStatus}</span></p>
            <p>Continuity ratio: {(TRUST_CHAIN_INTEGRITY.continuityRatio * 100).toFixed(1)}%</p>
            <p>Broken segments: {TRUST_CHAIN_INTEGRITY.brokenSegments}</p>
            <p>Blocked reports: {TRUST_CHAIN_INTEGRITY.blockedReports}</p>
            <p className="text-muted-foreground">Last verified: {TRUST_CHAIN_INTEGRITY.lastVerifiedAt} by {TRUST_CHAIN_INTEGRITY.verifier}</p>
          </div>
        </Card>

        <Card title="Governance approval risk" titleSize="sm" variant="elevated" accent="warning" className="border-warning/40">
          <SourceStateBadge state={approvalRiskSource.state} reason={approvalRiskSource.reason} compact />
          <div className="space-y-1 text-xs">
            <p>Pending policy: <span className="font-semibold">{GOVERNANCE_APPROVAL.pendingVersion}</span></p>
            <p>Status: <span className="font-semibold text-warning">{GOVERNANCE_APPROVAL.status}</span></p>
            <p>Risk delta: {GOVERNANCE_APPROVAL.policyRiskDelta}</p>
            <p className="text-muted-foreground">Missing approvers: {GOVERNANCE_APPROVAL.missingApprovers.join(", ")}</p>
          </div>
        </Card>
      </section>

      <section aria-label="health security posture" className="rounded-xl border border-warning/40 bg-warning/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-warning">/health security posture (mandatory) <SourceStateBadge state={healthPostureSource.state} reason={healthPostureSource.reason} compact className="ml-2" /></p>
        <ul className="mt-2 space-y-1 text-xs">
          <li>Encryption algorithm: <span className="font-semibold">{HEALTH_SECURITY_POSTURE.encryptionAlgorithm}</span></li>
          <li>Authentication mode: <span className="font-semibold">{HEALTH_SECURITY_POSTURE.authenticationMode}</span></li>
          <li>Direct FUJI API: <span className="font-semibold">{HEALTH_SECURITY_POSTURE.directFujiApi}</span></li>
        </ul>
      </section>

      <section aria-label={`${title} operational cards`} className="grid gap-4 md:grid-cols-3">
        {OPS_PRIORITY_ITEMS.map((item, index) => (
          <OpsPriorityCard key={item.key} item={item} priority={index + 1} sourceState="fixture" sourceStateReason="deterministic_fixture" />
        ))}
      </section>

      <section className="grid gap-4 md:grid-cols-2" aria-label="replay and evidence routing">
        <Card title="Replay diff readability" titleSize="sm" variant="glass" className="border-border/70" accent="danger">
          <SourceStateBadge state={replayDiffSource.state} reason={replayDiffSource.reason} compact />
          <div className="space-y-1 text-xs">
            <p>Status: <span className="font-semibold text-danger">{REPLAY_DIFF_INSIGHT.status}</span></p>
            <p>Changed fields: {REPLAY_DIFF_INSIGHT.changedFields.join(", ")}</p>
            <p>Safety-sensitive fields: <span className="font-semibold">{REPLAY_DIFF_INSIGHT.safetySensitiveFields.join(", ")}</span></p>
            <p className="text-muted-foreground">{t(REPLAY_DIFF_INSIGHT.operatorActionJa, REPLAY_DIFF_INSIGHT.operatorActionEn)}</p>
          </div>
        </Card>

        <Card title="Risk → Decision → Evidence → Report" titleSize="sm" variant="glass" className="border-border/70" accent="info">
          <SourceStateBadge state={evidenceRouteSource.state} reason={evidenceRouteSource.reason} compact />
          <ol className="list-decimal space-y-1 pl-4 text-xs">
            <li><span className="font-semibold">Risk:</span> {DECISION_EVIDENCE_ROUTE.riskSignal}</li>
            <li><span className="font-semibold">Decision:</span> {DECISION_EVIDENCE_ROUTE.decisionTarget}</li>
            <li><span className="font-semibold">Evidence:</span> {DECISION_EVIDENCE_ROUTE.evidenceAnchor}</li>
            <li><span className="font-semibold">Report:</span> {DECISION_EVIDENCE_ROUTE.reportingTarget}</li>
          </ol>
        </Card>

        <Card title="Policy diff / impact preview" titleSize="sm" variant="glass" className="border-border/70" accent="warning">
          <SourceStateBadge state={policyPreviewSource.state} reason={policyPreviewSource.reason} compact />
          <div className="space-y-1 text-xs">
            <p>Status: <span className="font-semibold text-warning">{POLICY_DIFF_IMPACT_PREVIEW.status}</span></p>
            <p>{POLICY_DIFF_IMPACT_PREVIEW.summary}</p>
            <p className="text-muted-foreground">Route: {POLICY_DIFF_IMPACT_PREVIEW.previewTarget}</p>
          </div>
        </Card>
      </section>

      <section className="rounded-xl border border-border/70 bg-muted/20 p-4" aria-label={t("空状態ガイド", "Empty state guide")}>
        <p className="text-xs text-muted-foreground">
          {t(
            "低アクティビティ時でもこの画面は異常監視の司令塔です。FUJI reject・replay mismatch・policy update pending・broken hash chain・risk burst を継続監視し、異常発生時は Decision / TrustLog / Governance / Risk へ1クリックで遷移します。",
            "Even in low activity, this page remains the command center. It continuously monitors FUJI reject, replay mismatch, policy update pending, broken hash chain, and risk burst, and provides one-click transitions to Decision / TrustLog / Governance / Risk.",
          )}
        </p>
      </section>
    </div>
  );
}
