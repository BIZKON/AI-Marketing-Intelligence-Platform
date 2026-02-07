"use client";

import { useEffect, useState } from "react";
import { getToken } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

interface GamificationProfile {
  level: string;
  xp: number;
  coins: number;
  current_streak: number;
  longest_streak: number;
}

interface Challenge {
  id: string;
  type: string;
  label: string;
  target: number;
  progress: number;
  reward_coins: number;
  is_completed: boolean;
}

interface ShopItem {
  id: string;
  name: string;
  price: number;
  type: string;
}

interface LevelInfo {
  name: string;
  min_xp: number;
  label: string;
}

export default function GamificationPage() {
  const { t } = useI18n();
  const [profile, setProfile] = useState<GamificationProfile | null>(null);
  const [challenges, setChallenges] = useState<Challenge[]>([]);
  const [shopItems, setShopItems] = useState<ShopItem[]>([]);
  const [levels, setLevels] = useState<LevelInfo[]>([]);
  const [leaderboard, setLeaderboard] = useState<
    { user_name: string; level: string; xp: number; current_streak: number }[]
  >([]);
  const [loading, setLoading] = useState(true);
  const [purchaseMsg, setPurchaseMsg] = useState<string | null>(null);

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    const token = getToken();
    if (!token) return;
    const headers = { Authorization: `Bearer ${token}` };

    try {
      const [profileRes, challengesRes, shopRes, levelsRes, lbRes] = await Promise.all([
        fetch(`${API_BASE}/gamification/profile`, { headers }),
        fetch(`${API_BASE}/gamification/challenges`, { headers }),
        fetch(`${API_BASE}/gamification/shop`, { headers }),
        fetch(`${API_BASE}/gamification/levels`, { headers }),
        fetch(`${API_BASE}/gamification/leaderboard?limit=10`, { headers }),
      ]);
      setProfile(await profileRes.json());
      setChallenges(await challengesRes.json());
      setShopItems(await shopRes.json());
      setLevels(await levelsRes.json());
      setLeaderboard(await lbRes.json());
    } catch {
    } finally {
      setLoading(false);
    }
  };

  const purchaseItem = async (itemId: string) => {
    const token = getToken();
    if (!token) return;
    setPurchaseMsg(null);
    try {
      const res = await fetch(`${API_BASE}/gamification/shop/${itemId}/purchase`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const err = await res.json();
        setPurchaseMsg(err.detail || t("gamification", "purchaseFailed"));
        return;
      }
      setPurchaseMsg(t("gamification", "purchased"));
      fetchAll();
    } catch {
      setPurchaseMsg(t("gamification", "purchaseFailed"));
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  const currentLevel = levels.find((l) => l.name === profile?.level);
  const nextLevel = levels.find((l) => l.min_xp > (profile?.xp || 0));
  const xpProgress = nextLevel
    ? ((profile?.xp || 0) - (currentLevel?.min_xp || 0)) /
      (nextLevel.min_xp - (currentLevel?.min_xp || 0))
    : 1;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("gamification", "title")}
          </h1>
          <LanguageSwitcher />
        </div>

        {/* Profile Card */}
        {profile && (
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 mb-6">
            <div className="flex items-center justify-between mb-4">
              <div>
                <span className="text-sm text-gray-500 dark:text-gray-400">{t("gamification", "level")}</span>
                <h2 className="text-2xl font-bold text-blue-600 capitalize">
                  {currentLevel?.label || profile.level}
                </h2>
              </div>
              <div className="flex gap-6 text-center">
                <div>
                  <div className="text-2xl font-bold text-yellow-500">{profile.coins}</div>
                  <div className="text-xs text-gray-500">{t("gamification", "coins")}</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-orange-500">{profile.current_streak}</div>
                  <div className="text-xs text-gray-500">{t("gamification", "streak")}</div>
                </div>
                <div>
                  <div className="text-2xl font-bold text-purple-500">{profile.xp}</div>
                  <div className="text-xs text-gray-500">{t("gamification", "xp")}</div>
                </div>
              </div>
            </div>
            {/* XP Progress bar */}
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-3">
              <div
                className="bg-blue-600 h-3 rounded-full transition-all"
                style={{ width: `${Math.min(xpProgress * 100, 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>{profile.xp} {t("gamification", "xp")}</span>
              <span>{nextLevel ? t("gamification", "xpFor", { xp: nextLevel.min_xp, level: nextLevel.label }) : t("gamification", "maxLevel")}</span>
            </div>
          </div>
        )}

        <div className="grid md:grid-cols-2 gap-6">
          {/* Challenges */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6">
            <h2 className="text-lg font-semibold mb-4 dark:text-white">{t("gamification", "dailyChallenges")}</h2>
            {challenges.length === 0 ? (
              <p className="text-gray-400 text-center py-4">{t("gamification", "noChallenges")}</p>
            ) : (
              <div className="space-y-3">
                {challenges.map((c) => (
                  <div
                    key={c.id}
                    className={`p-3 rounded-lg border ${
                      c.is_completed
                        ? "border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-900/20"
                        : "border-gray-200 dark:border-gray-700"
                    }`}
                  >
                    <div className="flex justify-between items-start">
                      <span className={`text-sm ${c.is_completed ? "line-through text-gray-400" : "dark:text-white"}`}>
                        {c.label}
                      </span>
                      <span className="text-xs font-semibold text-yellow-600">
                        {t("gamification", "coinsReward", { coins: c.reward_coins })}
                      </span>
                    </div>
                    <div className="mt-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                      <div
                        className={`h-2 rounded-full ${c.is_completed ? "bg-green-500" : "bg-blue-500"}`}
                        style={{ width: `${Math.min((c.progress / c.target) * 100, 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Shop */}
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6">
            <h2 className="text-lg font-semibold mb-4 dark:text-white">{t("gamification", "shop")}</h2>
            {purchaseMsg && (
              <div className="mb-3 p-2 text-sm rounded bg-blue-100 text-blue-700">{purchaseMsg}</div>
            )}
            <div className="space-y-3">
              {shopItems.map((item) => (
                <div
                  key={item.id}
                  className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700"
                >
                  <div>
                    <div className="text-sm font-medium dark:text-white">{item.name}</div>
                    <div className="text-xs text-gray-500 capitalize">{item.type}</div>
                  </div>
                  <button
                    onClick={() => purchaseItem(item.id)}
                    disabled={(profile?.coins || 0) < item.price}
                    className="px-3 py-1 text-sm bg-yellow-500 text-white rounded-lg hover:bg-yellow-600 disabled:opacity-50"
                  >
                    {item.price} {t("gamification", "coins").toLowerCase()}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Leaderboard */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-6 mt-6">
          <h2 className="text-lg font-semibold mb-4 dark:text-white">{t("gamification", "xpLeaderboard")}</h2>
          {leaderboard.length === 0 ? (
            <p className="text-gray-400 text-center py-4">{t("common", "noData")}</p>
          ) : (
            <div className="space-y-2">
              {leaderboard.map((entry, i) => (
                <div
                  key={i}
                  className="flex items-center justify-between p-3 rounded-lg bg-gray-50 dark:bg-gray-700"
                >
                  <div className="flex items-center gap-3">
                    <span className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold ${
                      i === 0 ? "bg-yellow-400 text-yellow-900" :
                      i === 1 ? "bg-gray-300 text-gray-700" :
                      i === 2 ? "bg-orange-300 text-orange-900" :
                      "bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-300"
                    }`}>
                      {i + 1}
                    </span>
                    <div>
                      <div className="text-sm font-medium dark:text-white">{entry.user_name}</div>
                      <div className="text-xs text-gray-500 capitalize">{entry.level}</div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-sm font-bold text-purple-600">{entry.xp} {t("gamification", "xp")}</div>
                    <div className="text-xs text-orange-500">{t("gamification", "dayStreak", { days: entry.current_streak })}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
