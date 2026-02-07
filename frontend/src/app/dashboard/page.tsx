"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type { CompetitorResponse, SubscriptionResponse, ContentTaskResponse } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

interface DashboardData {
  competitors: CompetitorResponse[];
  tasks: ContentTaskResponse[];
  subscription: SubscriptionResponse | null;
}

export default function Dashboard() {
  const router = useRouter();
  const { t } = useI18n();
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    // Auth guard: redirect to home if not authenticated (#058)
    if (!token) {
      router.replace("/");
      return;
    }

    async function fetchData() {
      try {
        const [competitors, tasks, subscription] = await Promise.all([
          api.getCompetitors(token!).catch(() => [] as CompetitorResponse[]),
          api.getTasks(token!).catch(() => [] as ContentTaskResponse[]),
          api.getSubscription(token!).catch(() => null),
        ]);
        setData({ competitors, tasks, subscription });
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : t("dashboard", "failedToLoad");
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">{t("common", "loading")}</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-red-500">{error}</p>
      </div>
    );
  }

  const competitorCount = data?.competitors.length ?? 0;
  const taskCount = data?.tasks.length ?? 0;
  const plan = data?.subscription?.plan ?? "monitor";

  return (
    <div className="min-h-screen">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                {t("dashboard", "title")}
              </h1>
              <LanguageSwitcher />
            </div>
            <nav className="flex gap-4">
              <Link href="/dashboard" className="text-sm font-medium text-brand-600">{t("dashboard", "overview")}</Link>
              <Link href="/dashboard/competitors" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("dashboard", "competitors")}</Link>
              <Link href="/dashboard/content" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("dashboard", "content")}</Link>
              <Link href="/dashboard/reports" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("dashboard", "reports")}</Link>
              <Link href="/training" className="text-sm font-medium text-gray-500 hover:text-gray-700">{t("common", "training")}</Link>
            </nav>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Stats cards */}
        <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          <StatsCard title={t("dashboard", "competitors")} value={String(competitorCount)} description={t("dashboard", "beingTracked")} />
          <StatsCard title={t("dashboard", "reports")} value="-" description={t("dashboard", "thisMonth")} />
          <StatsCard title={t("dashboard", "contentTasks")} value={String(taskCount)} description={t("dashboard", "inPipeline")} />
          <StatsCard title={t("dashboard", "plan")} value={plan.charAt(0).toUpperCase() + plan.slice(1)} description={t("dashboard", "currentSubscription")} />
        </div>

        {/* Placeholder sections */}
        <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t("dashboard", "competitorActivity")}</h2>
            <p className="mt-2 text-sm text-gray-500">{t("dashboard", "activityCharts")}</p>
          </div>
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t("dashboard", "recentReports")}</h2>
            <p className="mt-2 text-sm text-gray-500">{t("dashboard", "recentReportsPlaceholder")}</p>
          </div>
        </div>
      </main>
    </div>
  );
}

function StatsCard({ title, value, description }: { title: string; value: string; description: string }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
      <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
      <p className="mt-1 text-3xl font-semibold text-gray-900 dark:text-white">{value}</p>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{description}</p>
    </div>
  );
}
