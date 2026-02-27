"use client";

import { useEffect } from "react";

type GlobalErrorPageProps = {
  error: Error & { digest?: string };
  reset: () => void;
};

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

  return (
    <main className="mx-auto flex min-h-[60vh] max-w-2xl flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-3xl font-semibold text-zinc-100">問題が発生しました</h1>
      <p className="text-sm text-zinc-300">
        予期しないエラーが発生しました。しばらくしてから再試行してください。
      </p>
      <button
        className="rounded-md border border-zinc-600 bg-zinc-900 px-4 py-2 text-sm font-medium text-zinc-100 transition hover:bg-zinc-800"
        onClick={() => reset()}
        type="button"
      >
        再試行
      </button>
    </main>
  );
}
