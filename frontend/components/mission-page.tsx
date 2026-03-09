import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
}

type SystemHealth = "health" | "degraded" | "critical";

interface HealthMetric {
  labelJa: string;
  labelEn: string;
  value: string;
  state: SystemHealth;
  detailJa: string;
  detailEn: string;
  href: string;
}

interface CriticalRailItem {
  key: string;
  label: string;
  severity: "critical" | "degraded";
  delta: string;
  href: string;
}

interface OperationalCard {
  titleJa: string;
  titleEn: string;
  owner: string;
  riskRank: number;
  summaryJa: string;
  summaryEn: string;
  ctaJa: string;
  ctaEn: string;
  href: string;
}

const HEALTH_STYLE: Record<SystemHealth, string> = {
  health: "text-success",
  degraded: "text-warning",
  critical: "text-danger",
};

const SYSTEM_HEALTH_METRICS: HealthMetric[] = [
  {
    labelJa: "Decision Pipeline",
    labelEn: "Decision Pipeline",
    value: "critical",
    state: "critical",
    detailJa: "FUJI reject が通常比 2.4x。手動審査キュー増加。",
    detailEn: "FUJI rejects are 2.4x baseline. Manual review queue is growing.",
    href: "/console",
  },
  {
    labelJa: "TrustLog Integrity",
    labelEn: "TrustLog Integrity",
    value: "degraded",
    state: "degraded",
    detailJa: "replay mismatch が 3 件。broken chain 監視を強化中。",
    detailEn: "3 replay mismatches detected. Intensifying broken-chain watch.",
    href: "/audit",
  },
  {
    labelJa: "Governance Drift",
    labelEn: "Governance Drift",
    value: "health",
    state: "health",
    detailJa: "policy update は適用済み。承認フロー整合性は維持。",
    detailEn: "Policy updates are applied. Approval flow integrity is healthy.",
    href: "/governance",
  },
];

const CRITICAL_RAIL_ITEMS: CriticalRailItem[] = [
  {
    key: "fuji-reject",
    label: "FUJI reject",
    severity: "critical",
    delta: "+12 / 15m",
    href: "/console",
  },
  {
    key: "replay-mismatch",
    label: "Replay mismatch",
    severity: "critical",
    delta: "3 active",
    href: "/audit",
  },
  {
    key: "policy-update",
    label: "policy update",
    severity: "degraded",
    delta: "pending sign-off",
    href: "/governance",
  },
  {
    key: "broken-chain",
    label: "broken chain",
    severity: "critical",
    delta: "2 segments",
    href: "/audit",
  },
  {
    key: "risk-burst",
    label: "risk burst",
    severity: "critical",
    delta: "p99 +38%",
    href: "/risk",
  },
];

const OPERATIONAL_CARDS: OperationalCard[] = [
  {
    titleJa: "#1 最優先: FUJI拒否トリアージ",
    titleEn: "#1 Highest risk: FUJI reject triage",
    owner: "Planner + Fuji",
    riskRank: 1,
    summaryJa: "同一 policy_id で拒否が連鎖。誤拒否と真性危険を30分以内に切り分け。",
    summaryEn: "Reject cascades on one policy_id. Separate false rejects from real risk within 30 minutes.",
    ctaJa: "Decision を開く",
    ctaEn: "Open Decision",
    href: "/console",
  },
  {
    titleJa: "#2 Replay整合性復旧",
    titleEn: "#2 Replay integrity recovery",
    owner: "Kernel + TrustLog",
    riskRank: 2,
    summaryJa: "replay mismatch と broken chain を突合し、監査鎖の連続性を復旧。",
    summaryEn: "Correlate replay mismatch and broken chain to restore audit-chain continuity.",
    ctaJa: "TrustLog を確認",
    ctaEn: "Review TrustLog",
    href: "/audit",
  },
  {
    titleJa: "#3 Policy rollout監視",
    titleEn: "#3 Policy rollout watch",
    owner: "Governance",
    riskRank: 3,
    summaryJa: "直近 policy update に対する影響範囲と risk burst の波及を追跡。",
    summaryEn: "Track impact radius of recent policy updates and downstream risk burst.",
    ctaJa: "Governance へ",
    ctaEn: "Open Governance",
    href: "/governance",
  },
];

/**
 * MissionPage renders the command-center summary with explicit risk priority.
 *
 * It replaces abstract previews with operational cards so operators can identify
 * the highest-risk issue and drill down immediately.
 */
export function MissionPage({ title, subtitle, chips }: MissionPageProps): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <Card
        title={title}
        titleSize="lg"
        variant="glass"
        description={subtitle}
        className="border-primary/20"
        accent="primary"
      >
        <div className="flex flex-wrap gap-2">
          {chips.map((chip) => (
            <span
              key={chip}
              aria-hidden="true"
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/8 px-3 py-1 text-xs font-medium text-primary"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              {chip}
            </span>
          ))}
        </div>
      </Card>

      <section aria-label="critical rail" className="rounded-xl border border-danger/30 bg-danger/8 p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-danger">Critical Rail</p>
          <a href="/risk" className="rounded-md border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger">
            {t("危険度順で開く", "Open by risk priority")}
          </a>
        </div>
        <div className="grid gap-2 md:grid-cols-5">
          {CRITICAL_RAIL_ITEMS.map((item) => (
            <a
              key={item.key}
              href={item.href}
              className="rounded-lg border border-danger/20 bg-background/60 px-3 py-2 text-xs transition-colors hover:bg-background"
            >
              <p className="font-semibold text-foreground">{item.label}</p>
              <p className={item.severity === "critical" ? "text-danger" : "text-warning"}>{item.delta}</p>
            </a>
          ))}
        </div>
      </section>

      <section aria-label={t("全体ヘルス", "System health")} className="grid gap-3 md:grid-cols-3">
        {SYSTEM_HEALTH_METRICS.map((metric) => (
          <a key={metric.labelEn} href={metric.href} className="rounded-lg border border-border/60 bg-card/70 p-3">
            <div className="flex items-center justify-between text-xs">
              <span>{t(metric.labelJa, metric.labelEn)}</span>
              <span className={`font-mono font-semibold ${HEALTH_STYLE[metric.state]}`}>{metric.value}</span>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{t(metric.detailJa, metric.detailEn)}</p>
          </a>
        ))}
      </section>

      <section aria-label={`${title} operational cards`} className="grid gap-4 md:grid-cols-3">
        {OPERATIONAL_CARDS.map((card) => (
          <Card
            key={card.titleEn}
            title={t(card.titleJa, card.titleEn)}
            titleSize="sm"
            variant="elevated"
            accent={card.riskRank === 1 ? "danger" : card.riskRank === 2 ? "warning" : "info"}
            className="border-border/60"
          >
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Owner: {card.owner}</p>
              <p className="text-sm">{t(card.summaryJa, card.summaryEn)}</p>
              <a href={card.href} className="inline-flex rounded border border-border px-2 py-1 text-xs font-medium">
                {t(card.ctaJa, card.ctaEn)}
              </a>
            </div>
          </Card>
        ))}
      </section>

      <section className="rounded-xl border border-border/70 bg-muted/20 p-4" aria-label={t("空状態ガイド", "Empty state guide")}>
        <p className="text-xs text-muted-foreground">
          {t(
            "イベントが無い時間帯でも、この画面は FUJI拒否・リプレイ不一致・統制変更・リスク急騰を常時監視し、Decision / TrustLog / Governance / Risk へ即遷移する司令塔です。",
            "Even in quiet periods, this screen continuously monitors FUJI rejects, replay mismatches, governance changes, and risk bursts, then routes instantly to Decision / TrustLog / Governance / Risk.",
          )}
        </p>
      </section>
    </div>
  );
}
