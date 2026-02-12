import { Card } from "@veritas/design-system";

interface MissionPageProps {
  title: string;
  subtitle: string;
  chips: [string, string, string];
}

export function MissionPage({ title, subtitle, chips }: MissionPageProps): JSX.Element {
  return (
    <div className="space-y-6">
      <Card title={title} className="border-primary/50 bg-surface/85">
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </Card>

      <section aria-label={`${title} intelligence grid`} className="grid gap-4 md:grid-cols-3">
        {chips.map((chip) => (
          <Card key={chip} title={chip} className="bg-background/75">
            <div className="h-24 rounded-md border border-dashed border-primary/40 bg-primary/5" />
          </Card>
        ))}
      </section>
    </div>
  );
}
