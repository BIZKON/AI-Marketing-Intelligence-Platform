"use client";

import { useI18n, Locale } from "@/i18n/context";

const LOCALES: { value: Locale; flag: string; label: string }[] = [
  { value: "ru", flag: "RU", label: "Русский" },
  { value: "en", flag: "EN", label: "English" },
];

export function LanguageSwitcher() {
  const { locale, setLocale } = useI18n();

  return (
    <button
      onClick={() => setLocale(locale === "ru" ? "en" : "ru")}
      className="inline-flex items-center gap-1.5 rounded-md border border-gray-300 px-2.5 py-1 text-xs font-medium text-gray-700 hover:bg-gray-50 transition-colors dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
      title={LOCALES.find((l) => l.value !== locale)?.label}
    >
      <span>{LOCALES.find((l) => l.value === locale)?.flag}</span>
      <svg className="w-3 h-3 opacity-50" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    </button>
  );
}
