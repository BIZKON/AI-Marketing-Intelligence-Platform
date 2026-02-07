"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

interface MultiplayerSession {
  id: string;
  session_code: string;
  status: string;
  max_participants: number;
}

export default function MultiplayerPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [tab, setTab] = useState<"create" | "join">("create");
  const [scenarios, setScenarios] = useState<{ id: string; title: string }[]>([]);
  const [selectedScenario, setSelectedScenario] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [session, setSession] = useState<MultiplayerSession | null>(null);
  const [leaderboard, setLeaderboard] = useState<
    { user_name: string; avg_score: number; sessions_count: number }[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api.getScenarios(token).then(setScenarios).catch(() => {});
    fetchLeaderboard();
  }, []);

  const fetchLeaderboard = async () => {
    const token = getToken();
    if (!token) return;
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/multiplayer/leaderboard/top?limit=10`,
        { headers: { Authorization: `Bearer ${token}` } }
      );
      if (res.ok) setLeaderboard(await res.json());
    } catch {}
  };

  const createSession = async () => {
    if (!selectedScenario) return;
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/multiplayer/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ scenario_id: selectedScenario, max_participants: 5 }),
        }
      );
      if (!res.ok) throw new Error();
      setSession(await res.json());
    } catch {
      setError(t("multiplayerPage", "failedToCreate"));
    } finally {
      setLoading(false);
    }
  };

  const joinSession = async () => {
    if (!joinCode.trim()) return;
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/multiplayer/join`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ session_code: joinCode.trim().toUpperCase() }),
        }
      );
      if (!res.ok) throw new Error();
      const data = await res.json();
      setSession({ id: data.session_id, session_code: joinCode, status: "waiting", max_participants: 5 });
    } catch {
      setError(t("multiplayerPage", "failedToJoin"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("multiplayerPage", "title")}
          </h1>
          <LanguageSwitcher />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-lg">{error}</div>
        )}

        {session ? (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 text-center">
            <h2 className="text-xl font-semibold mb-2 dark:text-white">{t("multiplayerPage", "sessionCreated")}</h2>
            <p className="text-gray-500 dark:text-gray-400 mb-4">{t("multiplayerPage", "shareCode")}</p>
            <div className="text-4xl font-mono font-bold text-blue-600 tracking-widest mb-4">
              {session.session_code}
            </div>
            <p className="text-sm text-gray-500 mb-6">
              {t("multiplayerPage", "statusInfo", { status: session.status, count: session.max_participants })}
            </p>
            <button
              onClick={() => setSession(null)}
              className="px-6 py-2 bg-gray-200 dark:bg-gray-700 rounded-lg hover:bg-gray-300 dark:hover:bg-gray-600 dark:text-white"
            >
              {t("common", "back")}
            </button>
          </div>
        ) : (
          <div className="grid md:grid-cols-2 gap-6">
            {/* Create / Join */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6">
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setTab("create")}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium ${
                    tab === "create"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  }`}
                >
                  {t("multiplayerPage", "createSession")}
                </button>
                <button
                  onClick={() => setTab("join")}
                  className={`flex-1 py-2 rounded-lg text-sm font-medium ${
                    tab === "join"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300"
                  }`}
                >
                  {t("multiplayerPage", "joinSession")}
                </button>
              </div>

              {tab === "create" ? (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                      {t("multiplayerPage", "selectScenario")}
                    </label>
                    <select
                      value={selectedScenario}
                      onChange={(e) => setSelectedScenario(e.target.value)}
                      className="w-full px-3 py-2 border rounded-lg dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                    >
                      <option value="">{t("multiplayerPage", "choose")}</option>
                      {scenarios.map((s) => (
                        <option key={s.id} value={s.id}>{s.title}</option>
                      ))}
                    </select>
                  </div>
                  <button
                    onClick={createSession}
                    disabled={loading || !selectedScenario}
                    className="w-full py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
                  >
                    {loading ? t("multiplayerPage", "creating") : t("multiplayerPage", "createSession")}
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm text-gray-600 dark:text-gray-400 mb-1">
                      {t("multiplayerPage", "sessionCode")}
                    </label>
                    <input
                      type="text"
                      value={joinCode}
                      onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                      maxLength={6}
                      className="w-full px-3 py-2 border rounded-lg text-center text-2xl font-mono tracking-widest dark:bg-gray-700 dark:border-gray-600 dark:text-white"
                      placeholder="ABCDEF"
                    />
                  </div>
                  <button
                    onClick={joinSession}
                    disabled={loading || joinCode.length < 6}
                    className="w-full py-3 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50 font-medium"
                  >
                    {loading ? t("multiplayerPage", "joining") : t("multiplayerPage", "joinButton")}
                  </button>
                </div>
              )}
            </div>

            {/* Leaderboard */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6">
              <h2 className="text-lg font-semibold mb-4 dark:text-white">{t("multiplayerPage", "leaderboard")}</h2>
              {leaderboard.length === 0 ? (
                <p className="text-gray-400 text-center py-8">{t("common", "noData")}</p>
              ) : (
                <div className="space-y-2">
                  {leaderboard.map((entry, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between p-2 rounded-lg bg-gray-50 dark:bg-gray-700"
                    >
                      <div className="flex items-center gap-3">
                        <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                          i === 0 ? "bg-yellow-400 text-yellow-900" :
                          i === 1 ? "bg-gray-300 text-gray-700" :
                          i === 2 ? "bg-orange-300 text-orange-900" :
                          "bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300"
                        }`}>
                          {i + 1}
                        </span>
                        <span className="text-sm font-medium dark:text-white">
                          {entry.user_name}
                        </span>
                      </div>
                      <span className="text-sm text-blue-600 font-semibold">
                        {entry.avg_score?.toFixed(0) || "—"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
