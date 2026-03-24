"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { en } from "../locales/en";
import { ja, type LocaleKey } from "../locales/ja";

type Language = "ja" | "en";

interface I18nContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (ja: string, en: string) => string;
  tk: (key: LocaleKey) => string;
}

const defaultI18nContext: I18nContextValue = {
  language: "ja",
  setLanguage: () => undefined,
  t: (ja: string, en: string) => ja ?? en,
  tk: (key: LocaleKey) => ja[key],
};

const I18nContext = createContext<I18nContextValue>(defaultI18nContext);

export function I18nProvider({ children }: { children: React.ReactNode }): JSX.Element {
  const [language, setLanguage] = useState<Language>("ja");

  useEffect(() => {
    try {
      const storedLanguage = window.localStorage.getItem("veritas_language");
      if (storedLanguage === "ja" || storedLanguage === "en") {
        setLanguage(storedLanguage);
      }
    } catch {
      // localStorage unavailable (private browsing, quota exceeded, etc.)
    }

    const handleStorage = (e: StorageEvent) => {
      if (e.key === "veritas_language" && (e.newValue === "ja" || e.newValue === "en")) {
        setLanguage(e.newValue);
      }
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem("veritas_language", language);
    } catch {
      // localStorage unavailable
    }
    document.documentElement.lang = language;
  }, [language]);

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t: (ja: string, en: string) => (language === "ja" ? ja : en),
      tk: (key: LocaleKey) => (language === "ja" ? ja[key] : en[key]),
    }),
    [language],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  return useContext(I18nContext);
}
