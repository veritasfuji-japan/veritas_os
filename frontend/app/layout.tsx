import type { Metadata } from "next";
import { AppShell, ThemeStyles, applyThemeClass } from "@veritas/design-system";
import "./globals.css";

export const metadata: Metadata = {
  title: "Veritas UI",
  description: "Veritas monorepo frontend scaffold"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>): JSX.Element {
  return (
    <html className={applyThemeClass("light")} lang="ja">
      <body>
        <ThemeStyles />
        <AppShell
          description="共通レイアウトとアクセシブルなデザイントークンを適用しています。"
          title="Veritas UI Workspace"
        >
          {children}
        </AppShell>
      </body>
    </html>
  );
}
