"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type { UserResponse } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export default function SettingsPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [user, setUser] = useState<UserResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  // Form fields
  const [fullName, setFullName] = useState("");
  const [brandName, setBrandName] = useState("");
  const [brandIndustry, setBrandIndustry] = useState("");
  const [brandDescription, setBrandDescription] = useState("");
  const [toneOfVoice, setToneOfVoice] = useState("");
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    // Load dark mode preference
    const dm = localStorage.getItem("darkMode") === "true";
    setDarkMode(dm);
    if (dm) document.documentElement.classList.add("dark");

    async function fetchUser() {
      try {
        const userData = await api.getMe(token!);
        setUser(userData);
        setFullName(userData.full_name || "");
        setBrandName(userData.brand_name || "");
        setBrandIndustry(userData.brand_industry || "");
        setBrandDescription(userData.brand_description || "");
        setToneOfVoice(userData.tone_of_voice || "");
      } catch (err) {
        const msg = err instanceof ApiError ? err.detail : t("settings", "failedToLoad");
        setMessage(msg);
      } finally {
        setLoading(false);
      }
    }

    fetchUser();
  }, [router]);

  function toggleDarkMode() {
    const newVal = !darkMode;
    setDarkMode(newVal);
    localStorage.setItem("darkMode", String(newVal));
    if (newVal) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }

  function resetOnboarding() {
    localStorage.removeItem("training_onboarded");
    setMessage(t("settings", "onboardingReset"));
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">{t("settings", "loadingSettings")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-3xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">{t("settings", "title")}</h1>
            <div className="flex items-center gap-3">
              <LanguageSwitcher />
              <Link href="/dashboard" className="text-sm font-medium text-gray-500 hover:text-gray-700">
                {t("settings", "backToDashboard")}
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6 lg:px-8">
        {message && (
          <div className="mb-6 rounded-lg bg-blue-50 p-4 text-sm text-blue-700 dark:bg-blue-950 dark:text-blue-300">
            {message}
          </div>
        )}

        {/* Profile Section */}
        <section className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t("settings", "profile")}</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("settings", "fullName")}</label>
              <input
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("settings", "email")}</label>
              <input
                type="email"
                value={user?.email || ""}
                disabled
                className="w-full rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500 dark:bg-gray-800 dark:border-gray-700"
              />
            </div>
          </div>
        </section>

        {/* Brand Section */}
        <section className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t("settings", "brandProfile")}</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("settings", "brandName")}</label>
              <input
                type="text"
                value={brandName}
                onChange={(e) => setBrandName(e.target.value)}
                placeholder={t("settings", "brandNamePlaceholder")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("settings", "industry")}</label>
              <input
                type="text"
                value={brandIndustry}
                onChange={(e) => setBrandIndustry(e.target.value)}
                placeholder={t("settings", "industryPlaceholder")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("settings", "description")}</label>
              <textarea
                value={brandDescription}
                onChange={(e) => setBrandDescription(e.target.value)}
                rows={3}
                placeholder={t("settings", "descriptionPlaceholder")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-white resize-none"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t("settings", "toneOfVoice")}</label>
              <input
                type="text"
                value={toneOfVoice}
                onChange={(e) => setToneOfVoice(e.target.value)}
                placeholder={t("settings", "tonePlaceholder")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm dark:bg-gray-800 dark:border-gray-600 dark:text-white"
              />
            </div>
          </div>
        </section>

        {/* Appearance */}
        <section className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t("settings", "appearance")}</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("settings", "darkMode")}</p>
              <p className="text-xs text-gray-500">{t("settings", "darkModeDescription")}</p>
            </div>
            <button
              onClick={toggleDarkMode}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                darkMode ? "bg-brand-600" : "bg-gray-300"
              }`}
            >
              <span
                className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${
                  darkMode ? "translate-x-6" : "translate-x-1"
                }`}
              />
            </button>
          </div>
        </section>

        {/* Training Settings */}
        <section className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 mb-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t("settings", "trainingSettings")}</h2>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{t("settings", "resetOnboarding")}</p>
              <p className="text-xs text-gray-500">{t("settings", "resetOnboardingDescription")}</p>
            </div>
            <button
              onClick={resetOnboarding}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800"
            >
              {t("common", "reset")}
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}
