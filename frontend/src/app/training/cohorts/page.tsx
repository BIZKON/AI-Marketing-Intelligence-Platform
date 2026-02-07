"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError, getToken } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

interface CohortEntry {
  cohort_label: string;
  user_count: number;
  total_sessions: number;
  completed_sessions: number;
  avg_score: number | null;
  avg_sessions_per_user: number;
  completion_rate: number;
}

interface LeaderboardEntry {
  user_id: string;
  display_name: string;
  sessions: number;
  avg_score: number | null;
  best_score: number | null;
  level: string;
  xp: number;
}

interface UserRank {
  rank: number;
  total_users: number;
  percentile: number;
  total_sessions: number;
  completed_sessions: number;
  avg_score: number | null;
}

async function apiFetch<T>(endpoint: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(res.status, err.detail);
  }
  return res.json();
}

export default function CohortAnalyticsPage() {
  const router = useRouter();
  const [tab, setTab] = useState<"registration" | "plan" | "leaderboard">("registration");
  const [cohorts, setCohorts] = useState<CohortEntry[]>([]);
  const [leaderboard, setLeaderboard] = useState<LeaderboardEntry[]>([]);
  const [myRank, setMyRank] = useState<UserRank | null>(null);
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
        const [regData, planData, lb, rank] = await Promise.all([
          apiFetch<CohortEntry[]>("/cohorts/by-registration", token!),
          apiFetch<CohortEntry[]>("/cohorts/by-plan", token!),
          apiFetch<LeaderboardEntry[]>("/cohorts/leaderboard", token!),
          apiFetch<UserRank>("/cohorts/my-rank", token!),
        ]);
        setCohorts(tab === "plan" ? planData : regData);
        setLeaderboard(lb);
        setMyRank(rank);
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Failed to load cohort data");
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, [router, tab]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">Loading cohort analytics...</p>
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

  return (
    <div className="min-h-screen">
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
        <div className="mx-auto max-w-7xl px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
              Cohort Analytics
            </h1>
            <nav className="flex gap-4">
              <Link href="/training/analytics" className="text-sm font-medium text-gray-500 hover:text-gray-700">My Analytics</Link>
              <Link href="/training/cohorts" className="text-sm font-medium text-indigo-600">Cohorts</Link>
              <Link href="/training" className="text-sm font-medium text-gray-500 hover:text-gray-700">Scenarios</Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* My Rank */}
        {myRank && (
          <div className="mb-6 rounded-lg border border-indigo-200 bg-indigo-50 p-4 dark:bg-indigo-950 dark:border-indigo-800">
            <div className="flex items-center gap-6">
              <div>
                <p className="text-sm text-indigo-600 dark:text-indigo-400">Your Rank</p>
                <p className="text-3xl font-bold text-indigo-700 dark:text-indigo-300">#{myRank.rank}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">of {myRank.total_users} users</p>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">Top {myRank.percentile}%</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Avg Score</p>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">{myRank.avg_score ?? "—"}</p>
              </div>
              <div>
                <p className="text-sm text-gray-500">Sessions</p>
                <p className="text-lg font-semibold text-gray-900 dark:text-white">{myRank.total_sessions}</p>
              </div>
            </div>
          </div>
        )}

        {/* Tabs */}
        <div className="flex gap-2 mb-6">
          {(["registration", "plan", "leaderboard"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-indigo-600 text-white"
                  : "bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-300"
              }`}
            >
              {t === "registration" ? "By Registration" : t === "plan" ? "By Plan" : "Leaderboard"}
            </button>
          ))}
        </div>

        {/* Cohort Table */}
        {tab !== "leaderboard" ? (
          <div className="rounded-lg border border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800 overflow-hidden">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">Cohort</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Users</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Sessions</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Avg Score</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Sess/User</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Completion %</th>
                </tr>
              </thead>
              <tbody>
                {cohorts.map((c) => (
                  <tr key={c.cohort_label} className="border-t border-gray-100 dark:border-gray-800">
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{c.cohort_label}</td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{c.user_count}</td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{c.total_sessions}</td>
                    <td className="px-4 py-3 text-right font-medium text-gray-900 dark:text-white">
                      {c.avg_score ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{c.avg_sessions_per_user}</td>
                    <td className="px-4 py-3 text-right">
                      <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                        c.completion_rate >= 70 ? "bg-green-100 text-green-800" :
                        c.completion_rate >= 40 ? "bg-yellow-100 text-yellow-800" :
                        "bg-red-100 text-red-800"
                      }`}>
                        {c.completion_rate}%
                      </span>
                    </td>
                  </tr>
                ))}
                {cohorts.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-gray-500">
                      No cohort data available yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        ) : (
          /* Leaderboard */
          <div className="rounded-lg border border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800 overflow-hidden">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 dark:bg-gray-800">
                <tr>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">#</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">User</th>
                  <th className="text-left px-4 py-3 text-gray-500 font-medium">Level</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Sessions</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Avg Score</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">Best Score</th>
                  <th className="text-right px-4 py-3 text-gray-500 font-medium">XP</th>
                </tr>
              </thead>
              <tbody>
                {leaderboard.map((e, idx) => (
                  <tr key={e.user_id} className="border-t border-gray-100 dark:border-gray-800">
                    <td className="px-4 py-3 font-bold text-gray-900 dark:text-white">
                      {idx + 1}
                    </td>
                    <td className="px-4 py-3 font-medium text-gray-900 dark:text-white">{e.display_name}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-800 dark:bg-indigo-900 dark:text-indigo-300">
                        {e.level}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{e.sessions}</td>
                    <td className="px-4 py-3 text-right font-medium text-gray-900 dark:text-white">
                      {e.avg_score ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">
                      {e.best_score ?? "—"}
                    </td>
                    <td className="px-4 py-3 text-right text-gray-600 dark:text-gray-400">{e.xp}</td>
                  </tr>
                ))}
                {leaderboard.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-4 py-8 text-center text-gray-500">
                      Not enough data for leaderboard (minimum 3 sessions per user).
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  );
}
