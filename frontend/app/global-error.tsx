"use client";

import { useEffect, useMemo } from "react";

type GlobalFatalErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

function detectLanguage(): "ja" | "en" {
  if (typeof navigator !== "undefined") {
    return navigator.language.startsWith("ja") ? "ja" : "en";
  }
  return "ja";
}

/**
 * Next.js App Router の致命的エラー境界。
 *
 * ルート `layout.tsx` を含む復旧不能な例外時にもフォールバックUIを表示し、
 * ユーザーが再試行できるようにする。
 */
export default function GlobalFatalErrorPage({
  error,
  reset,
}: GlobalFatalErrorPageProps): JSX.Element {
  useEffect(() => {
    console.error("Unhandled fatal app error:", error);
  }, [error]);

  const lang = useMemo(detectLanguage, []);

  return (
    <html lang={lang}>
      <body className="bg-zinc-950 text-zinc-100 antialiased">
        <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
          <h1 className="text-3xl font-semibold">
            {lang === "ja" ? "重大な問題が発生しました" : "A critical error occurred"}
          </h1>
          <p className="text-sm text-zinc-300">
            {lang === "ja"
              ? "アプリの表示を継続できませんでした。再試行しても解消しない場合は、管理者に連絡してください。"
              : "The application could not continue rendering. If retrying does not resolve the issue, please contact your administrator."}
          </p>
          <button
            className="rounded-md border border-zinc-600 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-800"
            onClick={() => reset()}
            type="button"
          >
            {lang === "ja" ? "再読み込み" : "Reload"}
          </button>
        </main>
      </body>
    </html>
  );
}
