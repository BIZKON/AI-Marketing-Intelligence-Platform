"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type { TrainingAnalyticsResponse } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

const CRITERIA_KEY_MAP: Record<string, string> = {
  greeting: "criteriaGreeting",
  listening: "criteriaListening",
  objection_handling: "criteriaObjectionHandling",
  product_knowledge: "criteriaProductKnowledge",
  closing: "criteriaClosing",
  tone_empathy: "criteriaToneEmpathy",
  script_adherence: "criteriaScriptAdherence",
};

const ACHIEVEMENT_ICONS: Record<string, string> = {
  first_session: "S",
  sessions_10: "10",
  sessions_50: "50",
  perfect_score: "!!",
  score_80_plus: "80",
  all_scenarios: "A",
  streak_7: "7d",
};

export default function TrainingAnalyticsPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [analytics, setAnalytics] = useState<TrainingAnalyticsResponse | null>(null);
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
        const data = await api.getTrainingAnalytics(token!);
        setAnalytics(data);
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : t("analyticsPage", "failedToLoad");
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
        <p className="text-gray-500">{t("analyticsPage", "loadingAnalytics")}</p>
      </div>
    );
  }

  if (error || !analytics) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-500">{error || t("analyticsPage", "failedToLoad")}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              {t("analyticsPage", "title")}
            </h1>
            <div className="flex items-center gap-4">
              <nav className="flex gap-4">
                <Link href="/dashboard" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "dashboard")}</Link>
                <Link href="/training" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "scenarios")}</Link>
                <Link href="/training/analytics" className="text-sm font-medium text-brand-600">{t("common", "analytics")}</Link>
                <Link href="/training/history" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "history")}</Link>
              </nav>
              <LanguageSwitcher />
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Stats Overview */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5 mb-8">
          <StatCard label={t("analyticsPage", "totalSessions")} value={String(analytics.total_sessions)} />
          <StatCard label={t("analyticsPage", "completed")} value={String(analytics.completed_sessions)} />
          <StatCard
            label={t("analyticsPage", "avgScore")}
            value={analytics.avg_score ? String(analytics.avg_score) : "—"}
            highlight={analytics.avg_score !== null && analytics.avg_score >= 70}
          />
          <StatCard
            label={t("analyticsPage", "bestScore")}
            value={analytics.best_score ? String(analytics.best_score) : "—"}
            highlight
          />
          <StatCard label={t("analyticsPage", "totalTime")} value={`${analytics.total_duration_minutes} ${t("common", "min")}`} />
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Criteria Averages */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {t("analyticsPage", "criteriaAverages")}
            </h2>
            {Object.keys(analytics.criteria_averages).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(analytics.criteria_averages).map(([key, value]) => (
                  <div key={key}>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-gray-700 dark:text-gray-300">
                        {CRITERIA_KEY_MAP[key] ? t("session", CRITERIA_KEY_MAP[key]) : key}
                      </span>
                      <span className="font-medium text-gray-900 dark:text-white">{value}</span>
                    </div>
                    <div className="w-full bg-gray-200 rounded-full h-2.5 dark:bg-gray-700">
                      <div
                        className={`h-2.5 rounded-full ${value >= 80 ? "bg-green-500" : value >= 60 ? "bg-yellow-500" : "bg-red-500"}`}
                        style={{ width: `${Math.min(100, value)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">{t("analyticsPage", "noCriteria")}</p>
            )}
          </div>

          {/* Weekly Progress */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              {t("analyticsPage", "weeklyProgress")}
            </h2>
            {analytics.weekly_stats.length > 0 ? (
              <div className="space-y-3">
                {analytics.weekly_stats.map((week) => (
                  <div
                    key={week.week_start}
                    className="flex items-center justify-between rounded-md bg-gray-50 px-3 py-2 dark:bg-gray-800"
                  >
                    <span className="text-sm text-gray-700 dark:text-gray-300">
                      {t("analyticsPage", "weekOf", { date: new Date(week.week_start).toLocaleDateString() })}
                    </span>
                    <div className="flex gap-4 text-sm">
                      <span className="text-gray-500">{t("analyticsPage", "sessionsCount", { count: week.sessions_count })}</span>
                      <span className="font-medium text-gray-900 dark:text-white">
                        {week.avg_score ? t("analyticsPage", "avg", { score: week.avg_score }) : "—"}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-500">{t("analyticsPage", "noWeeklyData")}</p>
            )}
          </div>
        </div>

        {/* Achievements */}
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {t("analyticsPage", "achievements")}
          </h2>
          {analytics.achievements.length > 0 ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6">
              {analytics.achievements.map((ach) => (
                <div
                  key={ach.id}
                  className="flex flex-col items-center rounded-lg border border-brand-200 bg-brand-50 p-3 dark:bg-brand-950 dark:border-brand-800"
                >
                  <div className="w-10 h-10 rounded-full bg-brand-600 text-white flex items-center justify-center text-xs font-bold mb-2">
                    {ACHIEVEMENT_ICONS[ach.achievement_type] || "?"}
                  </div>
                  <span className="text-xs text-center font-medium text-gray-700 dark:text-gray-300">
                    {ach.metadata_json?.name || ach.achievement_type}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-500">{t("analyticsPage", "noAchievements")}</p>
          )}
        </div>

        {/* Recent Sessions */}
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            {t("analyticsPage", "recentSessions")}
          </h2>
          {analytics.recent_sessions.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-gray-700">
                    <th className="text-left py-2 text-gray-500 font-medium">{t("analyticsPage", "date")}</th>
                    <th className="text-left py-2 text-gray-500 font-medium">{t("analyticsPage", "mode")}</th>
                    <th className="text-left py-2 text-gray-500 font-medium">{t("analyticsPage", "status")}</th>
                    <th className="text-left py-2 text-gray-500 font-medium">{t("analyticsPage", "duration")}</th>
                    <th className="text-right py-2 text-gray-500 font-medium">{t("analyticsPage", "action")}</th>
                  </tr>
                </thead>
                <tbody>
                  {analytics.recent_sessions.map((session) => (
                    <tr key={session.id} className="border-b border-gray-100 dark:border-gray-800">
                      <td className="py-2 text-gray-900 dark:text-white">
                        {new Date(session.created_at).toLocaleDateString()}
                      </td>
                      <td className="py-2 text-gray-600 dark:text-gray-400">{session.mode}</td>
                      <td className="py-2">
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
                      <td className="py-2 text-gray-600 dark:text-gray-400">
                        {session.duration_seconds
                          ? `${Math.floor(session.duration_seconds / 60)} ${t("common", "min")}`
                          : "—"}
                      </td>
                      <td className="py-2 text-right">
                        <Link
                          href={`/training/session/${session.id}`}
                          className="text-brand-600 hover:text-brand-500 font-medium"
                        >
                          {t("common", "view")}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm text-gray-500">{t("analyticsPage", "noSessions")}</p>
          )}
        </div>
      </main>
    </div>
  );
}

function StatCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${highlight ? "text-green-600" : "text-gray-900 dark:text-white"}`}>
        {value}
      </p>
    </div>
  );
}
