"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "../lib/utils";
import { useI18n } from "./i18n-provider";
import { TraceabilityRail } from "./traceability-rail";

/* ─── SVG icons ─── */

function IconDashboard({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <rect x="2" y="2" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <rect x="11" y="2" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <rect x="2" y="11" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
      <rect x="11" y="11" width="7" height="7" rx="1.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function IconConsole({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M3.5 6.5L7 10L3.5 13.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9 13.5H16.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <rect x="1.5" y="2.5" width="17" height="15" rx="2" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

function IconGovernance({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M10 2L17.5 6V10C17.5 13.866 14.1 17.396 10 18C5.9 17.396 2.5 13.866 2.5 10V6L10 2Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M7 10L9 12L13 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconAudit({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M5 2.5H13L17.5 7V17.5H5V2.5Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M12.5 2.5V7.5H17.5" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round" />
      <path d="M7.5 10.5H12.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <path d="M7.5 13H10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

function IconRisk({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10 6.5V10.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="10" cy="13" r="0.75" fill="currentColor" />
    </svg>
  );
}

function IconChevronRight({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <path d="M6 4L10 8L6 12" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconGlobe({ className }: { className?: string }): JSX.Element {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="1.25" />
      <path d="M2 8h12M8 2c-1.5 2-2.5 3.8-2.5 6s1 4 2.5 6M8 2c1.5 2 2.5 3.8 2.5 6s-1 4-2.5 6" stroke="currentColor" strokeWidth="1.25" />
    </svg>
  );
}

/* ─── Nav items config ─── */

const NAV_ITEMS = [
  {
    href: "/",
    label: "Command Dashboard",
    shortJa: "監視",
    shortEn: "Watch",
    descJa: "全体ヘルスとアラート",
    descEn: "System health & alerts",
    Icon: IconDashboard,
  },
  {
    href: "/console",
    label: "Decision Console",
    shortJa: "実行",
    shortEn: "Run",
    descJa: "意思決定フロー",
    descEn: "Decision pipeline",
    Icon: IconConsole,
  },
  {
    href: "/governance",
    label: "Governance Control",
    shortJa: "統制",
    shortEn: "Policy",
    descJa: "ポリシー運用",
    descEn: "Policy operations",
    Icon: IconGovernance,
  },
  {
    href: "/audit",
    label: "TrustLog Explorer",
    shortJa: "監査",
    shortEn: "Audit",
    descJa: "証跡と追跡",
    descEn: "Evidence & traceability",
    Icon: IconAudit,
  },
  {
    href: "/risk",
    label: "Risk Intelligence",
    shortJa: "予測",
    shortEn: "Risk",
    descJa: "先行リスク検知",
    descEn: "Early risk detection",
    Icon: IconRisk,
  },
];

/* ─── Header status bar config ─── */

const HEADER_METRICS = [
  {
    title: "Environment",
    valueJa: "本番準備済みサンドボックス",
    valueEn: "Production-ready Sandbox",
    status: "success" as const,
  },
  {
    title: "Connection",
    valueJa: "Neural Mesh 安定 · 99.982%",
    valueEn: "Neural Mesh Stable · 99.982%",
    status: "info" as const,
  },
  {
    title: "Latest Event",
    valueJa: "Policy Sync #4821 完了",
    valueEn: "Policy Sync #4821 Completed",
    status: "primary" as const,
  },
];

const STATUS_DOT: Record<typeof HEADER_METRICS[number]["status"], string> = {
  success: "bg-emerald-500",
  info: "bg-sky-500",
  primary: "bg-violet-500",
};

const STATUS_TEXT: Record<typeof HEADER_METRICS[number]["status"], string> = {
  success: "text-emerald-600 dark:text-emerald-400",
  info: "text-sky-600 dark:text-sky-400",
  primary: "text-violet-600 dark:text-violet-400",
};

interface MissionLayoutProps {
  children: React.ReactNode;
}

export function MissionLayout({ children }: MissionLayoutProps): JSX.Element {
  const pathname = usePathname();
  const { language, setLanguage, t } = useI18n();

  return (
    <>
      {/* ── Sidebar ── */}
      <aside
        aria-label={t("サイドバー", "Sidebar")}
        className="flex flex-col border-b border-sidebar-border bg-sidebar lg:row-span-full lg:border-b-0 lg:border-r"
      >
        {/* Skip link */}
        <a
          href="#main-content"
          className="sr-only z-[var(--ds-z-overlay)] rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ds-color-focus-ring))]"
        >
          {t("メインコンテンツへスキップ", "Skip to main content")}
        </a>

        {/* Brand ── */}
        <div className="flex items-center gap-3 border-b border-sidebar-border px-5 py-4">
          {/* Logo mark */}
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/15 ring-1 ring-primary/30">
            <svg viewBox="0 0 20 20" fill="none" className="h-4.5 w-4.5" aria-hidden="true">
              <path
                d="M10 2L17 6.2V13.8L10 18L3 13.8V6.2L10 2Z"
                fill="hsl(var(--ds-color-primary) / 0.2)"
                stroke="hsl(var(--ds-color-primary))"
                strokeWidth="1.5"
                strokeLinejoin="round"
              />
              <path d="M10 6V10L13 12" stroke="hsl(var(--ds-color-primary))" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] font-semibold uppercase tracking-[0.18em] text-sidebar-muted">
              Veritas OS
            </p>
            <p className="truncate text-sm font-semibold leading-tight text-sidebar-foreground">
              {t("統治OS", "Governance OS")}
            </p>
            <p className="truncate text-[10px] text-sidebar-muted">
              {t("可読性を優先した運用ビュー", "Operations view optimized for readability")}
            </p>
          </div>
          {/* Live indicator */}
          <div className="flex items-center gap-1.5 rounded-full border border-sidebar-border px-2 py-1">
            <span className="status-dot-live h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden="true" />
            <span className="text-[10px] font-medium uppercase tracking-wide text-sidebar-muted">Live</span>
          </div>
        </div>

        {/* Navigation ── */}
        <nav aria-label="Main navigation" className="flex-1 overflow-y-auto px-3 py-4">
          <div className="mb-2 px-2">
            <p className="text-[10px] font-semibold uppercase tracking-[0.15em] text-sidebar-muted">
              {t("ナビゲーション", "Navigation")}
            </p>
          </div>
          <div className="space-y-0.5">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;
              const { Icon } = item;

              return (
                <div key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "group relative flex items-center gap-3 rounded-lg px-3 py-2.5 transition-all duration-150",
                      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[hsl(var(--ds-color-focus-ring))] focus-visible:ring-offset-1 focus-visible:ring-offset-sidebar",
                      isActive
                        ? "bg-primary/12 text-primary"
                        : "text-sidebar-foreground hover:bg-white/5 hover:text-white",
                    )}
                  >
                    {/* Active bar */}
                    {isActive && (
                      <span
                        className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-primary"
                        aria-hidden="true"
                      />
                    )}

                    {/* Icon */}
                    <Icon
                      className={cn(
                        "h-[18px] w-[18px] shrink-0 transition-colors",
                        isActive ? "text-primary" : "text-sidebar-muted group-hover:text-sidebar-foreground",
                      )}
                    />

                    {/* Label */}
                    <div className="min-w-0 flex-1">
                      <p className={cn(
                        "text-sm font-medium leading-tight",
                        isActive && "text-primary",
                      )}>
                        {item.label}
                      </p>
                      <p className="truncate text-[11px] text-sidebar-muted">
                        {t(item.descJa, item.descEn)}
                      </p>
                    </div>

                    {/* Badge */}
                    <span className={cn(
                      "shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-widest",
                      isActive
                        ? "bg-primary/15 text-primary"
                        : "bg-white/5 text-sidebar-muted",
                    )}>
                      {t(item.shortJa, item.shortEn)}
                    </span>

                    {/* Hover chevron */}
                    {!isActive && (
                      <IconChevronRight className="h-3.5 w-3.5 shrink-0 text-sidebar-muted opacity-0 transition-opacity group-hover:opacity-100" />
                    )}
                  </Link>
                </div>
              );
            })}
          </div>
        </nav>

        {/* Sidebar footer ── */}
        <div className="border-t border-sidebar-border px-4 py-3">
          {/* Language selector */}
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <IconGlobe className="h-3.5 w-3.5 text-sidebar-muted" />
              <span className="text-[11px] text-sidebar-muted">
                {t("言語", "Language")}
              </span>
            </div>
            <select
              aria-label="Language"
              value={language}
              onChange={(event) => setLanguage(event.target.value as "ja" | "en")}
              className="rounded-md border border-sidebar-border bg-transparent px-2 py-1 text-[11px] text-sidebar-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              <option value="ja">日本語</option>
              <option value="en">English</option>
            </select>
          </div>
          {/* Version */}
          <p className="mt-2 text-[10px] text-sidebar-muted">
            Mission Control IA · v0.1
          </p>
        </div>
      </aside>

      {/* ── Header status bar ── */}
      <header className="min-w-0 border-b border-border/60 bg-surface/80 px-6 py-3 backdrop-blur-md">
        <div className="grid gap-3 md:grid-cols-3">
          {HEADER_METRICS.map((metric) => (
            <div
              key={metric.title}
              className="flex items-center gap-3 rounded-lg border border-border/50 bg-background/60 px-4 py-2.5 shadow-xs"
            >
              <span
                className={`h-2 w-2 shrink-0 rounded-full ${STATUS_DOT[metric.status]}`}
                aria-hidden="true"
              />
              <div className="min-w-0">
                <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
                  {metric.title}
                </p>
                <p className={`truncate text-xs font-medium ${STATUS_TEXT[metric.status]}`}>
                  {t(metric.valueJa, metric.valueEn)}
                </p>
              </div>
            </div>
          ))}
        </div>
        <TraceabilityRail />
      </header>

      {/* ── Main content ── */}
      <main id="main-content" className="min-w-0 overflow-y-auto p-6" tabIndex={-1}>
        {children}
      </main>
    </>
  );
}
