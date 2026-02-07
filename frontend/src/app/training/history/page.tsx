"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type { TrainingSessionResponse } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export default function TrainingHistoryPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [sessions, setSessions] = useState<TrainingSessionResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    async function fetchData() {
      try {
        const data = await api.getTrainingSessions(token!, 50);
        setSessions(data);
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : t("historyPage", "failedToLoad");
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [router, t]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">{t("historyPage", "loadingHistory")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              {t("historyPage", "title")}
            </h1>
            <div className="flex items-center gap-4">
              <nav className="flex gap-4">
                <Link href="/dashboard" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "dashboard")}</Link>
                <Link href="/training" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "scenarios")}</Link>
                <Link href="/training/analytics" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "analytics")}</Link>
                <Link href="/training/history" className="text-sm font-medium text-brand-600">{t("common", "history")}</Link>
              </nav>
              <LanguageSwitcher />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>
        )}

        {sessions.length > 0 ? (
          <div className="rounded-lg border border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800 overflow-hidden">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">{t("historyPage", "date")}</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">{t("historyPage", "mode")}</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">{t("historyPage", "status")}</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">{t("historyPage", "duration")}</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">{t("historyPage", "action")}</th>
                </tr>
              </thead>
              <tbody>
                {sessions.map((session) => (
                  <tr key={session.id} className="border-t border-gray-100 dark:border-gray-800">
                    <td className="px-4 py-3 text-gray-900 dark:text-white">
                      {new Date(session.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400 capitalize">{session.mode}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                          session.status === "completed"
                            ? "bg-green-100 text-green-800"
                            : session.status === "in_progress"
                            ? "bg-blue-100 text-blue-800"
                            : "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {session.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-gray-600 dark:text-gray-400">
                      {session.duration_seconds
                        ? `${Math.floor(session.duration_seconds / 60)}m ${session.duration_seconds % 60}s`
                        : "—"}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        href={`/training/session/${session.id}`}
                        className="text-brand-600 hover:text-brand-500 font-medium"
                      >
                        {session.status === "in_progress" ? t("common", "continue") : t("common", "view")}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center py-12">
            <p className="text-gray-500 mb-4">{t("historyPage", "noSessions")}</p>
            <Link
              href="/training"
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500"
            >
              {t("historyPage", "startTraining")}
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}
