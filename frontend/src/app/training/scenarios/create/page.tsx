"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import { useI18n } from "@/i18n/context";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

export default function CreateScenarioPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [type, setType] = useState("incoming_call");
  const [difficulty, setDifficulty] = useState("medium");
  const [clientName, setClientName] = useState("");
  const [clientAge, setClientAge] = useState("");
  const [clientMood, setClientMood] = useState("");
  const [clientBackground, setClientBackground] = useState("");
  const [objections, setObjections] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");

  const SCENARIO_TYPES = [
    { value: "incoming_call", label: t("training", "typeIncomingCall") },
    { value: "outbound_call", label: t("training", "typeOutboundCall") },
    { value: "partner_pitch", label: t("training", "typePartnerPitch") },
    { value: "objection_handling", label: t("training", "typeObjectionHandling") },
    { value: "closing", label: t("training", "typeClosing") },
  ];

  const DIFFICULTIES = [
    { value: "easy", label: t("training", "difficultyEasy") },
    { value: "medium", label: t("training", "difficultyMedium") },
    { value: "hard", label: t("training", "difficultyHard") },
  ];

  const generateWithAI = async () => {
    setGenerating(true);
    try {
      const token = getToken();
      if (!token) return;

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/training/scenarios`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            title: title || "AI Generated Scenario",
            description: description || `${type} scenario with ${difficulty} difficulty`,
            type,
            difficulty,
            client_persona: {
              name: clientName || "AI Client",
              age: clientAge ? parseInt(clientAge) : undefined,
              mood: clientMood || "neutral",
              background: clientBackground || undefined,
              objections: objections ? objections.split("\n").filter(Boolean) : [],
            },
            system_prompt: systemPrompt || undefined,
          }),
        }
      );

      if (!res.ok) throw new Error("Failed to create scenario");
      const data = await res.json();
      router.push(`/training`);
    } catch {
      setError(t("createScenario", "failedToGenerate"));
    } finally {
      setGenerating(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError(t("createScenario", "titleRequired"));
      return;
    }
    setLoading(true);
    setError(null);

    try {
      const token = getToken();
      if (!token) return;

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/training/scenarios`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({
            title,
            description,
            type,
            difficulty,
            client_persona: {
              name: clientName || "Client",
              age: clientAge ? parseInt(clientAge) : undefined,
              mood: clientMood || undefined,
              background: clientBackground || undefined,
              objections: objections ? objections.split("\n").filter(Boolean) : [],
            },
            system_prompt: systemPrompt || undefined,
          }),
        }
      );

      if (!res.ok) throw new Error("Failed to create");
      router.push("/training");
    } catch {
      setError(t("createScenario", "failedToCreate"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            {t("createScenario", "title")}
          </h1>
          <div className="flex items-center gap-3">
            <LanguageSwitcher />
            <button
              onClick={() => router.back()}
              className="text-gray-500 hover:text-gray-700"
            >
              {t("common", "cancel")}
            </button>
          </div>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-lg">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("createScenario", "titleLabel")}
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
              placeholder={t("createScenario", "titlePlaceholder")}
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("createScenario", "descriptionLabel")}
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
              placeholder={t("createScenario", "descriptionPlaceholder")}
            />
          </div>

          {/* Type + Difficulty */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t("createScenario", "typeLabel")}
              </label>
              <select
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
              >
                {SCENARIO_TYPES.map((st) => (
                  <option key={st.value} value={st.value}>{st.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                {t("createScenario", "difficultyLabel")}
              </label>
              <select
                value={difficulty}
                onChange={(e) => setDifficulty(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
              >
                {DIFFICULTIES.map((d) => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Client Persona */}
          <fieldset className="border rounded-lg p-4 dark:border-gray-700">
            <legend className="text-sm font-medium text-gray-700 dark:text-gray-300 px-2">
              {t("createScenario", "clientPersona")}
            </legend>
            <div className="grid grid-cols-2 gap-4 mt-2">
              <input
                type="text"
                value={clientName}
                onChange={(e) => setClientName(e.target.value)}
                className="px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                placeholder={t("createScenario", "namePlaceholder")}
              />
              <input
                type="number"
                value={clientAge}
                onChange={(e) => setClientAge(e.target.value)}
                className="px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                placeholder={t("createScenario", "agePlaceholder")}
              />
            </div>
            <div className="grid grid-cols-2 gap-4 mt-3">
              <input
                type="text"
                value={clientMood}
                onChange={(e) => setClientMood(e.target.value)}
                className="px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                placeholder={t("createScenario", "moodPlaceholder")}
              />
              <input
                type="text"
                value={clientBackground}
                onChange={(e) => setClientBackground(e.target.value)}
                className="px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
                placeholder={t("createScenario", "backgroundPlaceholder")}
              />
            </div>
            <textarea
              value={objections}
              onChange={(e) => setObjections(e.target.value)}
              rows={3}
              className="w-full mt-3 px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white"
              placeholder={t("createScenario", "objectionsPlaceholder")}
            />
          </fieldset>

          {/* System Prompt */}
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              {t("createScenario", "systemPromptLabel")}
            </label>
            <textarea
              value={systemPrompt}
              onChange={(e) => setSystemPrompt(e.target.value)}
              rows={4}
              className="w-full px-3 py-2 border rounded-lg dark:bg-gray-800 dark:border-gray-700 dark:text-white font-mono text-sm"
              placeholder={t("createScenario", "systemPromptPlaceholder")}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={loading}
              className="flex-1 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 font-medium"
            >
              {loading ? t("createScenario", "creating") : t("createScenario", "createButton")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
