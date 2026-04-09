"use client";

import { Card } from "@veritas/design-system";
import { CriticalRail } from "./critical-rail";
import { GlobalHealthSummary } from "./global-health-summary";
import { OpsPriorityCard } from "./ops-priority-card";
import { useI18n } from "./i18n-provider";
import {
  type CriticalRailMetric,
  type DecisionEvidenceRouteModel,
  type GlobalHealthSummaryModel,
  type GovernanceApprovalModel,
  type MissionUiState,
  type OpsPriorityItem,
  type ReplayDiffInsightModel,
  type TrustChainIntegrityModel,
} from "./dashboard-types";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
}

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
export function MissionPage({ title, subtitle, chips }: MissionPageProps): JSX.Element {
  const { t } = useI18n();
  const uiState: MissionUiState = TRUST_CHAIN_INTEGRITY.verificationStatus === "broken" ? "degraded" : "operational";

  const statusMessage = {
    loading: t("データ同期中: 信頼状態の確定前です。", "Syncing data: trust state not yet confirmed."),
    empty: t("監視データなし: オペレーター確認が必要です。", "No monitoring data: operator verification required."),
    degraded: t("degraded: 監査連鎖が断続し、レポート確定を一部停止しています。", "Degraded: audit-chain continuity is broken and report finalization is partially blocked."),
    operational: t("operational: 信頼連鎖は検証済みです。", "Operational: trust chain is verified."),
  }[uiState];

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

      <GlobalHealthSummary summary={GLOBAL_HEALTH_SUMMARY} />
      <CriticalRail items={CRITICAL_RAIL_ITEMS} />
      <section aria-label="mission control state" className="rounded-xl border border-border/70 bg-background/70 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">System state</p>
        <p className={["mt-1 text-sm font-semibold", uiState === "degraded" ? "text-danger" : "text-foreground"].join(" ")}>{statusMessage}</p>
      </section>

      <section className="grid gap-4 md:grid-cols-2" aria-label="trust and governance highlights">
        <Card title="Trust Chain Integrity" titleSize="sm" variant="elevated" accent="danger" className="border-danger/40">
          <div className="space-y-1 text-xs">
            <p>Verification: <span className="font-semibold text-danger">{TRUST_CHAIN_INTEGRITY.verificationStatus}</span></p>
            <p>Continuity ratio: {(TRUST_CHAIN_INTEGRITY.continuityRatio * 100).toFixed(1)}%</p>
            <p>Broken segments: {TRUST_CHAIN_INTEGRITY.brokenSegments}</p>
            <p>Blocked reports: {TRUST_CHAIN_INTEGRITY.blockedReports}</p>
            <p className="text-muted-foreground">Last verified: {TRUST_CHAIN_INTEGRITY.lastVerifiedAt} by {TRUST_CHAIN_INTEGRITY.verifier}</p>
          </div>
        </Card>

        <Card title="Governance approval risk" titleSize="sm" variant="elevated" accent="warning" className="border-warning/40">
          <div className="space-y-1 text-xs">
            <p>Pending policy: <span className="font-semibold">{GOVERNANCE_APPROVAL.pendingVersion}</span></p>
            <p>Status: <span className="font-semibold text-warning">{GOVERNANCE_APPROVAL.status}</span></p>
            <p>Risk delta: {GOVERNANCE_APPROVAL.policyRiskDelta}</p>
            <p className="text-muted-foreground">Missing approvers: {GOVERNANCE_APPROVAL.missingApprovers.join(", ")}</p>
          </div>
        </Card>
      </section>

      <section aria-label="health security posture" className="rounded-xl border border-warning/40 bg-warning/10 p-4">
        <p className="text-xs font-semibold uppercase tracking-wide text-warning">/health security posture (mandatory)</p>
        <ul className="mt-2 space-y-1 text-xs">
          <li>Encryption algorithm: <span className="font-semibold">{HEALTH_SECURITY_POSTURE.encryptionAlgorithm}</span></li>
          <li>Authentication mode: <span className="font-semibold">{HEALTH_SECURITY_POSTURE.authenticationMode}</span></li>
          <li>Direct FUJI API: <span className="font-semibold">{HEALTH_SECURITY_POSTURE.directFujiApi}</span></li>
        </ul>
      </section>

      <section aria-label={`${title} operational cards`} className="grid gap-4 md:grid-cols-3">
        {OPS_PRIORITY_ITEMS.map((item, index) => (
          <OpsPriorityCard key={item.key} item={item} priority={index + 1} />
        ))}
      </section>

      <section className="grid gap-4 md:grid-cols-2" aria-label="replay and evidence routing">
        <Card title="Replay diff readability" titleSize="sm" variant="glass" className="border-border/70" accent="danger">
          <div className="space-y-1 text-xs">
            <p>Status: <span className="font-semibold text-danger">{REPLAY_DIFF_INSIGHT.status}</span></p>
            <p>Changed fields: {REPLAY_DIFF_INSIGHT.changedFields.join(", ")}</p>
            <p>Safety-sensitive fields: <span className="font-semibold">{REPLAY_DIFF_INSIGHT.safetySensitiveFields.join(", ")}</span></p>
            <p className="text-muted-foreground">{t(REPLAY_DIFF_INSIGHT.operatorActionJa, REPLAY_DIFF_INSIGHT.operatorActionEn)}</p>
          </div>
        </Card>

        <Card title="Risk → Decision → Evidence → Report" titleSize="sm" variant="glass" className="border-border/70" accent="info">
          <ol className="list-decimal space-y-1 pl-4 text-xs">
            <li><span className="font-semibold">Risk:</span> {DECISION_EVIDENCE_ROUTE.riskSignal}</li>
            <li><span className="font-semibold">Decision:</span> {DECISION_EVIDENCE_ROUTE.decisionTarget}</li>
            <li><span className="font-semibold">Evidence:</span> {DECISION_EVIDENCE_ROUTE.evidenceAnchor}</li>
            <li><span className="font-semibold">Report:</span> {DECISION_EVIDENCE_ROUTE.reportingTarget}</li>
          </ol>
        </Card>

        <Card title="Policy diff / impact preview" titleSize="sm" variant="glass" className="border-border/70" accent="warning">
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
