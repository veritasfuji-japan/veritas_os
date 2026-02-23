"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n";

const NAV_ITEMS = [
  { href: "/", label: "Command Dashboard", shortKey: "nav.dashboard.short", descKey: "nav.dashboard.desc" },
  { href: "/console", label: "Decision Console", shortKey: "nav.console.short", descKey: "nav.console.desc" },
  { href: "/governance", label: "Governance Control", shortKey: "nav.governance.short", descKey: "nav.governance.desc" },
  { href: "/audit", label: "TrustLog Explorer", shortKey: "nav.audit.short", descKey: "nav.audit.desc" },
  { href: "/risk", label: "Risk Intelligence", shortKey: "nav.risk.short", descKey: "nav.risk.desc" }
];

interface MissionLayoutProps {
  children: React.ReactNode;
}

export function MissionLayout({ children }: MissionLayoutProps): JSX.Element {
  const pathname = usePathname();
  const { locale, setLocale, t } = useI18n();

  const headerMetrics = [
    { title: t("layout.environment"), value: t("layout.envValue"), tone: "text-emerald-600" },
    { title: t("layout.connection"), value: t("layout.connectionValue"), tone: "text-sky-600" },
    { title: t("layout.latestEvent"), value: t("layout.eventValue"), tone: "text-violet-600" }
  ];

  return (
    <>
      <aside
        aria-label={t("layout.sidebar")}
        className="border-b border-border/70 bg-surface/95 p-6 backdrop-blur-xl lg:row-span-full lg:border-b-0 lg:border-r"
      >
        <a
          href="#main-content"
          className="sr-only z-[var(--ds-z-overlay)] rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[hsl(var(--ds-color-focus-ring))]"
        >
          {t("layout.skipToMain")}
        </a>
        <div className="mb-8 rounded-xl border border-border/60 bg-background/70 p-4 shadow-sm">
          <p className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Mission Control IA</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">統治OS</h1>
          <p className="mt-2 text-sm text-muted-foreground">{t("layout.brandSubtitle")}</p>
        </div>
        <div className="mb-4 flex items-center justify-between rounded-xl border border-border/60 bg-background/70 p-3 text-xs">
          <span className="font-medium text-muted-foreground">{t("layout.language")}</span>
          <div className="flex rounded-md border border-border/70 bg-background">
            {(["ja", "en"] as const).map((nextLocale) => (
              <button
                key={nextLocale}
                type="button"
                onClick={() => setLocale(nextLocale)}
                className={[
                  "px-2 py-1 uppercase",
                  locale === nextLocale ? "bg-primary/20 text-foreground" : "text-muted-foreground"
                ].join(" ")}
              >
                {nextLocale}
              </button>
            ))}
          </div>
        </div>
        <nav aria-label="Main navigation" className="space-y-2">
          {NAV_ITEMS.map((item) => {
            const isActive = pathname === item.href;

            return (
              <Link
                key={item.href}
                href={item.href}
                className={[
                  "group block rounded-xl border px-4 py-3 transition-all duration-200",
                  "focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[hsl(var(--ds-color-focus-ring))]",
                  isActive
                    ? "border-primary/70 bg-primary/10 shadow-[0_8px_28px_hsl(var(--ds-color-primary)_/_0.18)]"
                    : "border-border/70 bg-background/70 hover:border-primary/50 hover:bg-background"
                ].join(" ")}
              >
                <div className="mb-1 flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-foreground">{item.label}</p>
                  <span className="rounded-full border border-border/80 bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {t(item.shortKey)}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{t(item.descKey)}</p>
              </Link>
            );
          })}
        </nav>
      </aside>

      <header className="min-w-0 border-b border-border/70 bg-surface/80 px-6 py-4 backdrop-blur-xl">
        <div className="grid gap-3 md:grid-cols-3">
          {headerMetrics.map((metric) => (
            <Card key={metric.title} title={metric.title} className="border-border/70 bg-background/75 p-4 shadow-sm">
              <p className={["text-xs uppercase tracking-wide", metric.tone].join(" ")}>{metric.value}</p>
            </Card>
          ))}
        </div>
      </header>
      <main id="main-content" className="min-w-0 p-6" tabIndex={-1}>
        {children}
      </main>
    </>
  );
}
