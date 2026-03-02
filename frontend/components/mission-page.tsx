import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
}

const CHIP_ACCENTS = ["primary", "success", "info"] as const;

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
              className="inline-flex items-center gap-1.5 rounded-full border border-primary/25 bg-primary/8 px-3 py-1 text-xs font-medium text-primary"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden="true" />
              {chip}
            </span>
          ))}
        </div>
      </Card>

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
                <span className="font-mono font-semibold text-foreground">Ready</span>
              </div>
              <div className="h-1 w-full overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-primary to-primary/60 transition-all"
                  style={{ width: `${60 + index * 12}%` }}
                  aria-hidden="true"
                />
              </div>

              {/* Preview placeholder */}
              <div className="flex h-14 items-center justify-center rounded-lg border border-dashed border-primary/30 bg-primary/4">
                <span className="text-[11px] text-muted-foreground">
                  {t(`Widget ${index + 1}: 運用プレビュー`, `Widget ${index + 1}: operational preview`)}
                </span>
              </div>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
