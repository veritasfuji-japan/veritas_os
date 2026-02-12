import type { Metadata } from "next";
import "./globals.css";
import { applyThemeClass } from "@veritas/design-system";

export const metadata: Metadata = {
  title: "Veritas UI",
  description: "Veritas monorepo frontend scaffold"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ja">
      <body className={applyThemeClass("light")}>{children}</body>
    </html>
  );
}
