import type { Metadata } from "next";
import { ThemeStyles, applyThemeClass } from "@veritas/design-system";
import { MissionLayout } from "../components/mission-layout";
import "./globals.css";

export const metadata: Metadata = {
  title: "Mission Control IA",
  description: "統治OSの運用コンソール"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>): JSX.Element {
  return (
    <html className={applyThemeClass("light")} lang="ja">
      <head>
        <ThemeStyles />
      </head>
      <body>
        <MissionLayout>{children}</MissionLayout>
      </body>
    </html>
  );
}
