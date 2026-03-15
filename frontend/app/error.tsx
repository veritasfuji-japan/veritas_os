"use client";

import { useEffect, useMemo } from "react";

type GlobalErrorPageProps = {
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
 * Next.js App Router のルートエラーバウンダリ。
 *
 * 予期しない実行時エラーで画面全体が崩壊することを防ぎ、
 * ユーザーに復旧操作（再試行）を提供する。
 */
export default function GlobalErrorPage({
  error,
  reset,
}: GlobalErrorPageProps): JSX.Element {
  useEffect(() => {
    console.error("Unhandled route error:", error);
  }, [error]);

  const lang = useMemo(detectLanguage, []);

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-3xl font-semibold text-zinc-100">
        {lang === "ja" ? "問題が発生しました" : "Something went wrong"}
      </h1>
      <p className="text-sm text-zinc-300">
        {lang === "ja"
          ? "予期しないエラーが発生しました。しばらくしてから再試行してください。"
          : "An unexpected error occurred. Please try again later."}
      </p>
      <button
        className="rounded-md border border-zinc-600 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-800"
        onClick={() => reset()}
        type="button"
      >
        {lang === "ja" ? "再試行" : "Retry"}
      </button>
    </main>
  );
}
