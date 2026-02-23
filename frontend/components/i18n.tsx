"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Locale = "ja" | "en";

type TranslationValue = string;

const TRANSLATIONS: Record<Locale, Record<string, TranslationValue>> = {
  ja: {
    "layout.skipToMain": "メインコンテンツへスキップ",
    "layout.sidebar": "サイドバー",
    "layout.brandSubtitle": "可読性を優先した運用ビュー",
    "layout.language": "言語",
    "layout.environment": "環境",
    "layout.connection": "接続",
    "layout.latestEvent": "最新イベント",
    "layout.envValue": "本番対応サンドボックス",
    "layout.connectionValue": "ニューラルメッシュ安定 · 99.982%",
    "layout.eventValue": "ポリシー同期 #4821 完了",
    "nav.dashboard.short": "監視",
    "nav.dashboard.desc": "全体ヘルスとアラート",
    "nav.console.short": "実行",
    "nav.console.desc": "意思決定フロー",
    "nav.governance.short": "統制",
    "nav.governance.desc": "ポリシー運用",
    "nav.audit.short": "監査",
    "nav.audit.desc": "証跡と追跡",
    "nav.risk.short": "予測",
    "nav.risk.desc": "先行リスク検知",
    "mission.widget": "ウィジェット {index}: 運用プレビュー",
    "page.dashboard.subtitle": "ミッション全体の健全性を俯瞰監視し、異常シグナルを即時に検出します。",
    "page.governance.subtitle": "規範ポリシーの適用状況を可視化し、逸脱を最小遅延で是正します。",
    "page.audit.subtitle": "追跡可能な証跡を集約し、すべての意思決定を検証可能に維持します。",
    "page.risk.subtitle": "先行指標とシナリオ推論により、未来リスクの予兆を可視化します。",
    "stream.title": "ライブイベントストリーム",
    "stream.apiBase": "API Base URL",
    "stream.apiKey": "APIキー",
    "stream.status": "状態",
    "stream.invalidUrl": "有効な API Base URL を入力してください。",
    "stream.securityWarning": "セキュリティ注意: EventSource の互換性のため API キーはクエリ文字列で送信されます。共有ログで本番シークレットを使わないでください。",
    "stream.clear": "イベントをクリア",
    "stream.waiting": "イベント待機中...",
    "stream.connected": "🟢 接続中",
    "stream.reconnecting": "🟡 再接続中",
    "stream.invalid": "🔴 URL不正"
  },
  en: {
    "layout.skipToMain": "Skip to main content",
    "layout.sidebar": "Sidebar",
    "layout.brandSubtitle": "Operational view focused on readability",
    "layout.language": "Language",
    "layout.environment": "Environment",
    "layout.connection": "Connection",
    "layout.latestEvent": "Latest Event",
    "layout.envValue": "Production-ready Sandbox",
    "layout.connectionValue": "Neural Mesh Stable · 99.982%",
    "layout.eventValue": "Policy Sync #4821 Completed",
    "nav.dashboard.short": "Watch",
    "nav.dashboard.desc": "Global health and alerts",
    "nav.console.short": "Exec",
    "nav.console.desc": "Decision pipeline",
    "nav.governance.short": "Control",
    "nav.governance.desc": "Policy operations",
    "nav.audit.short": "Audit",
    "nav.audit.desc": "Evidence and traceability",
    "nav.risk.short": "Forecast",
    "nav.risk.desc": "Early risk detection",
    "mission.widget": "Widget {index}: operational preview",
    "page.dashboard.subtitle": "Monitor mission-wide health and detect anomaly signals immediately.",
    "page.governance.subtitle": "Visualize policy enforcement posture and remediate drift with minimal delay.",
    "page.audit.subtitle": "Aggregate verifiable evidence and keep every decision traceable.",
    "page.risk.subtitle": "Use leading indicators and scenario reasoning to detect emerging future risks.",
    "stream.title": "Live Event Stream",
    "stream.apiBase": "API Base URL",
    "stream.apiKey": "API Key",
    "stream.status": "Status",
    "stream.invalidUrl": "Please enter a valid API Base URL.",
    "stream.securityWarning": "Security note: API key is sent in the query string for EventSource compatibility. Avoid using production secrets in shared logs.",
    "stream.clear": "Clear events",
    "stream.waiting": "Waiting for events...",
    "stream.connected": "🟢 connected",
    "stream.reconnecting": "🟡 reconnecting",
    "stream.invalid": "🔴 invalid url"
  }
};

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

interface I18nProviderProps {
  children: React.ReactNode;
}

export function I18nProvider({ children }: I18nProviderProps): JSX.Element {
  const [locale, setLocale] = useState<Locale>("ja");

  useEffect(() => {
    const stored = window.localStorage.getItem("veritas_locale");
    if (stored === "ja" || stored === "en") {
      setLocale(stored);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem("veritas_locale", locale);
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nContextValue>(
    () => ({
      locale,
      setLocale,
      t: (key, vars = {}) => {
        const table = TRANSLATIONS[locale];
        const raw = table[key] ?? TRANSLATIONS.en[key] ?? key;

        return Object.entries(vars).reduce(
          (nextText, [name, replacement]) => nextText.replace(`{${name}}`, String(replacement)),
          raw
        );
      }
    }),
    [locale]
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const value = useContext(I18nContext);
  if (!value) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return value;
}

