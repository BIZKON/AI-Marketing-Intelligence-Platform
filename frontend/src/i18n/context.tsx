"use client";

import { createContext, useContext, useState, useEffect, useCallback, ReactNode } from "react";
import en from "./locales/en.json";
import ru from "./locales/ru.json";

export type Locale = "en" | "ru";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const messages: Record<Locale, Record<string, any>> = { en, ru };

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (section: string, key: string, params?: Record<string, string | number>) => string;
}

const I18nContext = createContext<I18nContextValue | null>(null);

function resolve(obj: Record<string, unknown>, key: string): string | undefined {
  // Support dot-notation: "difficulty.easy" → obj["difficulty"]["easy"]
  const parts = key.split(".");
  let current: unknown = obj;
  for (const part of parts) {
    if (current == null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[part];
  }
  return typeof current === "string" ? current : undefined;
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("ru");

  useEffect(() => {
    const saved = localStorage.getItem("locale") as Locale | null;
    if (saved && (saved === "en" || saved === "ru")) {
      setLocaleState(saved);
    }
  }, []);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    localStorage.setItem("locale", newLocale);
    document.documentElement.lang = newLocale;
  }, []);

  const t = useCallback(
    (section: string, key: string, params?: Record<string, string | number>): string => {
      const sectionObj = messages[locale]?.[section];
      const fallbackObj = messages.en?.[section];
      const value = resolve(sectionObj, key) ?? resolve(fallbackObj, key) ?? key;
      if (!params) return value;
      return Object.entries(params).reduce(
        (result, [k, v]) => result.replace(`{${k}}`, String(v)),
        value
      );
    },
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
