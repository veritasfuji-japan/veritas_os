import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
}

export function MissionPage({ title, subtitle, chips }: MissionPageProps): JSX.Element {
  const { t } = useI18n();

  return (
    <div className="space-y-6">
      <Card title={title} className="border-border/70 bg-surface/85 p-1 shadow-sm">
        <p className="max-w-3xl text-sm leading-relaxed text-muted-foreground">{subtitle}</p>
      </Card>

      <section aria-label={`${title} intelligence grid`} className="grid gap-4 md:grid-cols-3">
        {chips.map((chip, index) => (
          <Card key={chip} title={chip} className="border-border/70 bg-background/80 shadow-sm">
            <div className="space-y-3">
              <div className="h-1.5 w-24 rounded-full bg-primary/65" />
              <div className="h-16 rounded-lg border border-dashed border-primary/40 bg-primary/5" />
              <p className="text-xs text-muted-foreground">{t(`Widget ${index + 1}: 運用プレビュー`, `Widget ${index + 1}: operational preview`)}</p>
            </div>
          </Card>
        ))}
      </section>
    </div>
  );
}
