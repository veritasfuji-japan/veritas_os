import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";
import { type OpsPriorityItem } from "./dashboard-types";

interface OpsPriorityCardProps {
  item: OpsPriorityItem;
  priority: number;
}

export function OpsPriorityCard({ item, priority }: OpsPriorityCardProps): JSX.Element {
  const { t } = useI18n();

  return (
    <Card
      title={t(item.titleJa, item.titleEn)}
      titleSize="sm"
      variant="elevated"
      accent={priority === 1 ? "danger" : priority === 2 ? "warning" : "info"}
      className="border-border/60"
    >
      <div className="space-y-2 text-sm">
        <p className="text-xs text-muted-foreground">Owner: {item.owner}</p>
        <p>
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Why now</span>
          <br />
          {t(item.whyNowJa, item.whyNowEn)}
        </p>
        <p>
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Impact window</span>
          <br />
          {t(item.impactWindowJa, item.impactWindowEn)}
        </p>
        <a href={item.href} className="inline-flex rounded border border-border px-2 py-1 text-xs font-semibold">
          {t(item.ctaJa, item.ctaEn)}
        </a>
      </div>
    </Card>
  );
}
