import { Card } from "@veritas/design-system";
import { CriticalRail } from "./critical-rail";
import { GlobalHealthSummary } from "./global-health-summary";
import { OpsPriorityCard } from "./ops-priority-card";
import { useI18n } from "./i18n-provider";
import {
  type CriticalRailMetric,
  type GlobalHealthSummaryModel,
  type OpsPriorityItem,
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

/**
 * MissionPage renders the operational command-center view.
 *
 * The page surfaces the highest-risk anomaly first, then gives direct
 * intervention cards so operators can transition from monitoring to action.
 */
export function MissionPage({ title, subtitle, chips }: MissionPageProps): JSX.Element {
  const { t } = useI18n();

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

      <section aria-label={`${title} operational cards`} className="grid gap-4 md:grid-cols-3">
        {OPS_PRIORITY_ITEMS.map((item, index) => (
          <OpsPriorityCard key={item.key} item={item} priority={index + 1} />
        ))}
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
