import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
}

const CHIP_ACCENTS = ["primary", "success", "info"] as const;
const CHIP_STATUS = ["critical", "healthy", "warning"] as const;

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
            </span>
          ))}
        </div>
      </Card>

      <section aria-label="critical rail" className="rounded-xl border border-danger/30 bg-danger/8 p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-danger">Critical Rail</p>
            <p className="mt-1 text-sm font-medium text-danger">
              {t("FUJI高リスク案件が急増。直近15分で6件が human review を要求。", "FUJI high-risk decisions are spiking. 6 cases require human review in the last 15 min.")}
            </p>
          </div>
          <a href="/console" className="rounded-md border border-danger/40 px-3 py-1.5 text-xs font-semibold text-danger">
            {t("Open triage queue", "Open triage queue")}
          </a>
        </div>
      </section>

      <section aria-label={`${title} intelligence grid`} className="grid gap-4 md:grid-cols-3">
        {chips.map((chip, index) => (
          <Card
            key={chip}
            title={chip}
            titleSize="sm"
            variant="elevated"
            accent={CHIP_ACCENTS[index]}
            className="border-border/60"
          >
            <div className="space-y-3">
              {/* Metric bar */}
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{t("ステータス", "Status")}</span>
                <span className="font-mono font-semibold text-foreground">{CHIP_STATUS[index]}</span>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary to-primary/60 transition-all"
                  style={{ width: `${60 + index * 12}%` }}
                  aria-hidden="true"
                />
              </div>

              {/* Preview placeholder */}
              <div className="rounded-lg border border-border/70 bg-background/70 p-2 text-[11px] text-muted-foreground">
                {index === 0 && t("request_id req-92af が連続拒否。再実行とポリシー確認が必要。", "request_id req-92af was rejected consecutively. Replay and policy verification required.")}
                {index === 1 && t("信頼性SLO: 99.982%。stage latency: Debateで+18%。", "Reliability SLO: 99.982%. Stage latency: Debate +18%.")}
                {index === 2 && t("TrustLog chain mismatch 0件。監査整合性は維持。", "TrustLog chain mismatch: 0. Audit integrity is maintained.")}
              </div>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
