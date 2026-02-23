"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Card } from "@veritas/design-system";
import { useI18n } from "./i18n-provider";

const NAV_ITEMS = [
  {
    href: "/",
    label: "Command Dashboard",
    shortJa: "監視",
    shortEn: "Watch",
    descJa: "全体ヘルスとアラート",
    descEn: "System health and alerts",
  },
  {
    href: "/console",
    label: "Decision Console",
    shortJa: "実行",
    shortEn: "Run",
    descJa: "意思決定フロー",
    descEn: "Decision pipeline",
  },
  {
    href: "/governance",
    label: "Governance Control",
    shortJa: "統制",
    shortEn: "Policy",
    descJa: "ポリシー運用",
    descEn: "Policy operations",
  },
  {
    href: "/audit",
    label: "TrustLog Explorer",
    shortJa: "監査",
    shortEn: "Audit",
    descJa: "証跡と追跡",
    descEn: "Evidence and traceability",
  },
  {
    href: "/risk",
    label: "Risk Intelligence",
    shortJa: "予測",
    shortEn: "Risk",
    descJa: "先行リスク検知",
    descEn: "Early risk detection",
  },
];

const HEADER_METRICS = [
  {
    title: "Environment",
    valueJa: "本番準備済みサンドボックス",
    valueEn: "Production-ready Sandbox",
    tone: "text-emerald-600",
  },
  {
    title: "Connection",
    valueJa: "Neural Mesh 安定 · 99.982%",
    valueEn: "Neural Mesh Stable · 99.982%",
    tone: "text-sky-600",
  },
  {
    title: "Latest Event",
    valueJa: "Policy Sync #4821 完了",
    valueEn: "Policy Sync #4821 Completed",
    tone: "text-violet-600",
  },
];

interface MissionLayoutProps {
  children: React.ReactNode;
}

export function MissionLayout({ children }: MissionLayoutProps): JSX.Element {
  const pathname = usePathname();
  const { language, setLanguage, t } = useI18n();

  return (
    <>
      <aside
        aria-label={t("サイドバー", "Sidebar")}
        className="border-b border-border/70 bg-surface/95 p-6 backdrop-blur-xl lg:row-span-full lg:border-b-0 lg:border-r"
      >
        <a
          href="#main-content"
          className="sr-only z-[var(--ds-z-overlay)] rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[hsl(var(--ds-color-focus-ring))]"
        >
          {t("メインコンテンツへスキップ", "Skip to main content")}
        </a>
        <div className="mb-8 rounded-xl border border-border/60 bg-background/70 p-4 shadow-sm">
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] uppercase tracking-[0.24em] text-muted-foreground">Mission Control IA</p>
            <label className="text-xs text-muted-foreground">
              <span className="mr-2">Lang</span>
              <select
                aria-label="Language"
                value={language}
                onChange={(event) => setLanguage(event.target.value as "ja" | "en")}
                className="rounded-md border border-border bg-background px-2 py-1"
              >
                <option value="ja">日本語</option>
                <option value="en">English</option>
              </select>
            </label>
          </div>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight">{t("統治OS", "Governance OS")}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("可読性を優先した運用ビュー", "Operations view optimized for readability")}
          </p>
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
                    : "border-border/70 bg-background/70 hover:border-primary/50 hover:bg-background",
                ].join(" ")}
              >
                <div className="mb-1 flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-foreground">{item.label}</p>
                  <span className="rounded-full border border-border/80 bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    {t(item.shortJa, item.shortEn)}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">{t(item.descJa, item.descEn)}</p>
              </Link>
            );
          })}
        </nav>
      </aside>

      <header className="min-w-0 border-b border-border/70 bg-surface/80 px-6 py-4 backdrop-blur-xl">
        <div className="grid gap-3 md:grid-cols-3">
          {HEADER_METRICS.map((metric) => (
            <Card key={metric.title} title={metric.title} className="border-border/70 bg-background/75 p-4 shadow-sm">
              <p className={["text-xs uppercase tracking-wide", metric.tone].join(" ")}>{t(metric.valueJa, metric.valueEn)}</p>
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
