"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type { AtlasCloudStatusResponse, TrainingPlatformStatsResponse } from "@/lib/api";

export default function MonitoringPage() {
  const router = useRouter();
  const [atlasStatus, setAtlasStatus] = useState<AtlasCloudStatusResponse | null>(null);
  const [trainingStats, setTrainingStats] = useState<TrainingPlatformStatsResponse | null>(null);
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
        const [atlas, stats] = await Promise.all([
          api.getAtlasCloudStatus(token!),
          api.getTrainingPlatformStats(token!),
        ]);
        setAtlasStatus(atlas);
        setTrainingStats(stats);
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : "Failed to load monitoring data";
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
    // Refresh every 30s
    const interval = setInterval(fetchData, 30_000);
    return () => clearInterval(interval);
  }, [router]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading monitoring data...</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              Platform Monitoring
            </h1>
            <Link
              href="/dashboard"
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300"
            >
              Dashboard
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">{error}</div>
        )}

        {/* Atlas Cloud Status */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Atlas Cloud AI Gateway
          </h2>
          {atlasStatus && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-4">
              <div className="rounded-lg border bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
                <p className="text-sm text-gray-500">Overall Status</p>
                <p className={`text-2xl font-bold ${
                  atlasStatus.overall === "healthy" ? "text-green-600" : "text-red-600"
                }`}>
                  {atlasStatus.overall === "healthy" ? "Healthy" : "Degraded"}
                </p>
              </div>
              <div className="rounded-lg border bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
                <p className="text-sm text-gray-500">Active Services</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {Object.keys(atlasStatus.services).length || "—"}
                </p>
              </div>
              <div className="rounded-lg border bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
                <p className="text-sm text-gray-500">Open Circuits</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {Object.values(atlasStatus.services).filter((s) => s.status === "open").length}
                </p>
              </div>
              <div className="rounded-lg border bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
                <p className="text-sm text-gray-500">Total Failures</p>
                <p className="text-2xl font-bold text-gray-900 dark:text-white">
                  {Object.values(atlasStatus.services).reduce((sum, s) => sum + s.failures, 0)}
                </p>
              </div>
            </div>
          )}

          {/* Service Details Table */}
          {atlasStatus && Object.keys(atlasStatus.services).length > 0 && (
            <div className="rounded-lg border bg-white dark:bg-gray-900 dark:border-gray-800 overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                <thead className="bg-gray-50 dark:bg-gray-800">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Service</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Failures</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Threshold</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Last Failure</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {Object.entries(atlasStatus.services).map(([name, svc]) => (
                    <tr key={name}>
                      <td className="px-4 py-3 text-sm font-medium text-gray-900 dark:text-white">{name}</td>
                      <td className="px-4 py-3 text-sm">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          svc.status === "closed"
                            ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
                            : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
                        }`}>
                          {svc.status === "closed" ? "OK" : "OPEN"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{svc.failures}</td>
                      <td className="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{svc.threshold}</td>
                      <td className="px-4 py-3 text-sm text-gray-500">
                        {svc.seconds_since_last_failure != null
                          ? `${Math.round(svc.seconds_since_last_failure)}s ago`
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {atlasStatus && Object.keys(atlasStatus.services).length === 0 && (
            <div className="rounded-lg border bg-white p-6 dark:bg-gray-900 dark:border-gray-800 text-center text-gray-500">
              No service activity recorded yet.
            </div>
          )}
        </section>

        {/* Training Platform Stats */}
        <section>
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
            Training Platform Statistics
          </h2>
          {trainingStats && (
            <>
              <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 mb-6">
                <StatCard label="Total Sessions" value={trainingStats.total_sessions} />
                <StatCard label="Completed" value={trainingStats.completed_sessions} />
                <StatCard label="In Progress" value={trainingStats.in_progress_sessions} />
                <StatCard
                  label="Completion Rate"
                  value={`${trainingStats.completion_rate}%`}
                  color={trainingStats.completion_rate >= 70 ? "green" : trainingStats.completion_rate >= 40 ? "yellow" : "red"}
                />
                <StatCard
                  label="Avg Score"
                  value={trainingStats.avg_score != null ? trainingStats.avg_score.toString() : "—"}
                  color={
                    trainingStats.avg_score != null
                      ? trainingStats.avg_score >= 80 ? "green" : trainingStats.avg_score >= 60 ? "yellow" : "red"
                      : undefined
                  }
                />
                <StatCard label="Unique Users" value={trainingStats.unique_users} />
                <StatCard label="Training Hours" value={trainingStats.total_training_hours} />
              </div>
            </>
          )}
        </section>
      </main>
    </div>
  );
}

function StatCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string | number;
  color?: "green" | "yellow" | "red";
}) {
  const colorClass = color === "green"
    ? "text-green-600"
    : color === "yellow"
      ? "text-yellow-600"
      : color === "red"
        ? "text-red-600"
        : "text-gray-900 dark:text-white";

  return (
    <div className="rounded-lg border bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-2xl font-bold ${colorClass}`}>{value}</p>
    </div>
  );
}
