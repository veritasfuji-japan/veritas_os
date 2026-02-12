import type { ReactNode } from "react";
import { cn } from "./utils";

interface AppShellProps {
  children: ReactNode;
  title: string;
  description?: string;
  className?: string;
}

/**
 * Shared full-screen app layout with keyboard-first navigation and landmarks.
 */
export function AppShell({
  children,
  title,
  description,
  className
}: AppShellProps): JSX.Element {
  return (
    <div className={cn("min-h-screen bg-background text-foreground", className)}>
      <a
        href="#main-content"
        className="sr-only z-[var(--ds-z-overlay)] rounded-md bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-[hsl(var(--ds-color-focus-ring))]"
      >
        メインコンテンツへスキップ
      </a>
      <header className="border-b border-border bg-surface/90 px-6 py-4 backdrop-blur" role="banner">
        <h1 className="text-xl font-semibold">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </header>
      <main id="main-content" className="mx-auto w-full max-w-5xl px-6 py-8" role="main" tabIndex={-1}>
        {children}
      </main>
    </div>
  );
}
