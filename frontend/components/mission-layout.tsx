"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Card } from "@veritas/design-system";

const NAV_ITEMS = [
  { href: "/", label: "Command Dashboard", short: "監視" },
  { href: "/console", label: "Decision Console", short: "実行" },
  { href: "/governance", label: "Governance Control", short: "統制" },
  { href: "/audit", label: "TrustLog Explorer", short: "監査" },
  { href: "/risk", label: "Risk Intelligence", short: "予測" }
];

interface MissionLayoutProps {
  children: React.ReactNode;
}

export function MissionLayout({ children }: MissionLayoutProps): JSX.Element {
  const pathname = usePathname();

  return (
    <div className="relative min-h-screen overflow-hidden bg-background text-foreground">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,_hsl(var(--ds-color-primary)/0.18),_transparent_56%)]" />
      <div className="relative grid min-h-screen grid-cols-1 lg:grid-cols-[280px_1fr]">
        <aside className="border-b border-border/80 bg-surface/95 p-6 backdrop-blur lg:border-b-0 lg:border-r">
          <div className="mb-8">
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Mission Control IA</p>
            <h1 className="mt-2 text-2xl font-semibold">統治OS</h1>
          </div>
          <nav aria-label="Main navigation" className="space-y-2">
            {NAV_ITEMS.map((item) => {
              const isActive = pathname === item.href;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={[
                    "block rounded-md border px-4 py-3 transition-all",
                    isActive
                      ? "border-primary bg-primary/15 text-foreground shadow-[0_0_0_1px_hsl(var(--ds-color-primary))]"
                      : "border-border/70 bg-background/60 text-muted-foreground hover:border-primary/60 hover:text-foreground"
                  ].join(" ")}
                >
                  <p className="text-sm font-semibold">{item.label}</p>
                  <p className="text-xs uppercase tracking-wide">{item.short}</p>
                </Link>
              );
            })}
          </nav>
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="border-b border-border/80 bg-surface/80 px-6 py-4 backdrop-blur">
            <div className="grid gap-3 md:grid-cols-3">
              <Card title="Environment" className="border-primary/40 bg-background/70 p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Production-ready Sandbox</p>
              </Card>
              <Card title="Connection" className="border-primary/40 bg-background/70 p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Neural Mesh Stable · 99.982%</p>
              </Card>
              <Card title="Latest Event" className="border-primary/40 bg-background/70 p-4">
                <p className="text-xs uppercase tracking-wide text-muted-foreground">Policy Sync #4821 Completed</p>
              </Card>
            </div>
          </header>
          <main className="flex-1 p-6">{children}</main>
        </div>
      </div>
    </div>
  );
}
