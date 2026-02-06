"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type { TrainingScenarioResponse, TrainingAnalyticsResponse } from "@/lib/api";

const DIFFICULTY_LABELS: Record<string, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

const DIFFICULTY_COLORS: Record<string, string> = {
  easy: "bg-green-100 text-green-800",
  medium: "bg-yellow-100 text-yellow-800",
  hard: "bg-red-100 text-red-800",
};

const TYPE_LABELS: Record<string, string> = {
  incoming_call: "Incoming Call",
  outbound_call: "Outbound Call",
  partner_pitch: "Partner Pitch",
  objection_handling: "Objection Handling",
  closing: "Closing",
};

export default function TrainingPage() {
  const router = useRouter();
  const [scenarios, setScenarios] = useState<TrainingScenarioResponse[]>([]);
  const [analytics, setAnalytics] = useState<TrainingAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      router.replace("/");
      return;
    }

    async function fetchData() {
      try {
        const [scenarioList, analyticsData] = await Promise.all([
          api.getScenarios(token!),
          api.getTrainingAnalytics(token!).catch(() => null),
        ]);
        setScenarios(scenarioList);
        setAnalytics(analyticsData);
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : "Failed to load training data";
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [router]);

  async function startSession(scenarioId: string) {
    const token = getToken();
    if (!token) return;
    setStarting(scenarioId);
    try {
      const session = await api.createTrainingSession(token, scenarioId);
      router.push(`/training/session/${session.id}`);
    } catch (err) {
      const message = err instanceof ApiError ? err.detail : "Failed to start session";
      setError(message);
      setStarting(null);
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading training scenarios...</p>
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
              Sales Training
            </h1>
            <nav className="flex gap-4 flex-wrap">
              <Link href="/dashboard" className="text-sm font-medium text-gray-500 hover:text-gray-700">Dashboard</Link>
              <Link href="/training" className="text-sm font-medium text-brand-600">Scenarios</Link>
              <Link href="/training/analytics" className="text-sm font-medium text-gray-500 hover:text-gray-700">Analytics</Link>
              <Link href="/training/history" className="text-sm font-medium text-gray-500 hover:text-gray-700">History</Link>
              <Link href="/training/multiplayer" className="text-sm font-medium text-gray-500 hover:text-gray-700">Multiplayer</Link>
              <Link href="/training/gamification" className="text-sm font-medium text-gray-500 hover:text-gray-700">Gamification</Link>
              <Link href="/training/ab-tests" className="text-sm font-medium text-gray-500 hover:text-gray-700">A/B Tests</Link>
              <Link href="/training/export" className="text-sm font-medium text-gray-500 hover:text-gray-700">Export</Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {error && (
          <div className="mb-6 rounded-lg bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        {/* Quick Stats */}
        {analytics && (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4 mb-8">
            <div className="rounded-lg border border-gray-200 bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
              <p className="text-sm text-gray-500">Total Sessions</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{analytics.total_sessions}</p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
              <p className="text-sm text-gray-500">Avg Score</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {analytics.avg_score ? `${analytics.avg_score}` : "—"}
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
              <p className="text-sm text-gray-500">Best Score</p>
              <p className="text-2xl font-bold text-green-600">
                {analytics.best_score ?? "—"}
              </p>
            </div>
            <div className="rounded-lg border border-gray-200 bg-white p-4 dark:bg-gray-900 dark:border-gray-800">
              <p className="text-sm text-gray-500">Achievements</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">{analytics.achievements.length}</p>
            </div>
          </div>
        )}

        {/* Scenarios Grid */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Training Scenarios</h2>
          <Link
            href="/training/scenarios/create"
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-500"
          >
            Create Scenario
          </Link>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {scenarios.map((scenario) => (
            <div
              key={scenario.id}
              className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 flex flex-col"
            >
              <div className="flex items-start justify-between mb-3">
                <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${DIFFICULTY_COLORS[scenario.difficulty] || "bg-gray-100 text-gray-800"}`}>
                  {DIFFICULTY_LABELS[scenario.difficulty] || scenario.difficulty}
                </span>
                <span className="text-xs text-gray-500">
                  {TYPE_LABELS[scenario.type] || scenario.type}
                </span>
              </div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-white mb-2">
                {scenario.title}
              </h3>
              <p className="text-sm text-gray-500 mb-3 flex-1">
                {scenario.description}
              </p>
              <div className="flex items-center gap-2 mb-4">
                <span className="text-xs text-gray-400">Client:</span>
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {scenario.client_persona.name}
                  {scenario.client_persona.age ? `, ${scenario.client_persona.age}` : ""}
                </span>
              </div>
              {scenario.tags && (
                <div className="flex flex-wrap gap-1 mb-4">
                  {scenario.tags.map((tag) => (
                    <span key={tag} className="inline-flex items-center rounded-md bg-gray-50 px-2 py-1 text-xs text-gray-600 ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:ring-gray-700">
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              <button
                onClick={() => startSession(scenario.id)}
                disabled={starting === scenario.id}
                className="w-full rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-brand-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {starting === scenario.id ? "Starting..." : "Start Training"}
              </button>
            </div>
          ))}
        </div>

        {scenarios.length === 0 && !error && (
          <div className="text-center py-12">
            <p className="text-gray-500">No training scenarios available.</p>
          </div>
        )}
      </main>
    </div>
  );
}
