"use client";

import { useEffect, useState, useRef, useCallback } from "react";
import { useRouter, useParams } from "next/navigation";
import Link from "next/link";
import { api, ApiError, getToken } from "@/lib/api";
import type {
  TrainingSessionDetailResponse,
  TrainingMessageResponse,
  TrainingEvaluationResponse,
} from "@/lib/api";
import { useTrainingWebSocket } from "@/hooks/useTrainingWebSocket";
import { useI18n } from "@/i18n/context";

export default function TrainingSessionPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = params.id as string;
  const token = getToken();
  const { t } = useI18n();

  const CRITERIA_LABELS: Record<string, string> = {
    greeting: t("session", "criteriaGreeting"),
    listening: t("session", "criteriaListening"),
    objection_handling: t("session", "criteriaObjectionHandling"),
    product_knowledge: t("session", "criteriaProductKnowledge"),
    closing: t("session", "criteriaClosing"),
    tone_empathy: t("session", "criteriaToneEmpathy"),
    script_adherence: t("session", "criteriaScriptAdherence"),
  };

  const [session, setSession] = useState<TrainingSessionDetailResponse | null>(null);
  const [messages, setMessages] = useState<TrainingMessageResponse[]>([]);
  const [evaluation, setEvaluation] = useState<TrainingEvaluationResponse | null>(null);
  const [inputText, setInputText] = useState("");
  const [sending, setSending] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const isActive = session?.status === "in_progress";

  // WebSocket connection — only when session is active
  const ws = useTrainingWebSocket(sessionId, token, isActive === true);
  const useWS = ws.status === "connected";

  // Load session initially
  useEffect(() => {
    if (!token) {
      router.replace("/");
      return;
    }

    async function fetchSession() {
      try {
        const data = await api.getTrainingSession(token!, sessionId);
        setSession(data);
        setMessages(data.messages);
        if (data.evaluation) {
          setEvaluation(data.evaluation);
        }
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : t("session", "failedToLoad");
        setError(message);
      } finally {
        setLoading(false);
      }
    }

    fetchSession();
  }, [router, sessionId, token]);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Handle WebSocket responses
  useEffect(() => {
    if (ws.lastUserMessage && ws.lastAssistantMessage) {
      setMessages((prev) => [...prev, ws.lastUserMessage!, ws.lastAssistantMessage!]);
      setSending(false);
    }
  }, [ws.lastUserMessage, ws.lastAssistantMessage]);

  // Handle WebSocket evaluation
  useEffect(() => {
    if (ws.evaluation) {
      setEvaluation(ws.evaluation);
      setSession((prev) => (prev ? { ...prev, status: "completed" } : prev));
      setCompleting(false);
    }
  }, [ws.evaluation]);

  // Handle WebSocket errors
  useEffect(() => {
    if (ws.error) {
      setError(ws.error);
      setSending(false);
      setCompleting(false);
    }
  }, [ws.error]);

  // Send message — WebSocket first, fallback to REST
  const sendMessage = useCallback(async () => {
    if (!token || !inputText.trim() || sending) return;

    const text = inputText.trim();
    setInputText("");
    setSending(true);
    setError(null);

    if (useWS) {
      ws.sendMessage(text);
      // Response handled by WebSocket effect above
    } else {
      // REST fallback
      try {
        const result = await api.sendTrainingMessage(token, sessionId, text);
        setMessages((prev) => [...prev, result.user_message, result.assistant_message]);
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : t("session", "failedToSend");
        setError(message);
        setInputText(text);
      } finally {
        setSending(false);
      }
    }
  }, [token, inputText, sending, useWS, ws, sessionId]);

  // Complete session — WebSocket first, fallback to REST
  const completeSession = useCallback(async () => {
    if (!token || completing) return;

    setCompleting(true);
    setError(null);

    if (useWS) {
      ws.complete();
      // Response handled by WebSocket effect above
    } else {
      // REST fallback
      try {
        const result = await api.completeTrainingSession(token, sessionId);
        setEvaluation(result);
        setSession((prev) => (prev ? { ...prev, status: "completed" } : prev));
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : t("session", "failedToComplete");
        setError(message);
      } finally {
        setCompleting(false);
      }
    }
  }, [token, completing, useWS, ws, sessionId]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <p className="text-gray-500">{t("session", "loadingSession")}</p>
      </div>
    );
  }

  const clientName = session?.scenario?.client_persona?.name || "Client";

  // Show evaluation view
  if (evaluation) {
    return (
      <div className="min-h-screen">
        <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800">
          <div className="mx-auto max-w-4xl px-4 py-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between">
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">
                {t("session", "sessionResults")}
              </h1>
              <div className="flex gap-3">
                <Link
                  href="/training"
                  className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500 transition-colors"
                >
                  {t("session", "newTraining")}
                </Link>
                <Link
                  href="/training/analytics"
                  className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors dark:border-gray-600 dark:text-gray-300"
                >
                  {t("common", "analytics")}
                </Link>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
          {/* Overall Score */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center justify-center w-32 h-32 rounded-full border-4 border-brand-600 mb-4">
              <span className="text-4xl font-bold text-gray-900 dark:text-white">
                {evaluation.overall_score ?? 0}
              </span>
            </div>
            <p className="text-lg text-gray-600 dark:text-gray-400">{t("session", "overallScore")}</p>
            {evaluation.mood_analysis && (
              <p className="text-sm text-gray-500 mt-1">
                {t("session", "clientMood")} <span className="font-medium">{evaluation.mood_analysis}</span>
              </p>
            )}
          </div>

          {/* Criteria Breakdown */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 mb-6">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">{t("session", "criteriaBreakdown")}</h2>
            <div className="space-y-3">
              {Object.entries(evaluation.criteria_scores).map(([key, score]) => (
                <div key={key}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-700 dark:text-gray-300">{CRITERIA_LABELS[key] || key}</span>
                    <span className="font-medium text-gray-900 dark:text-white">{score}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2 dark:bg-gray-700">
                    <div
                      className={`h-2 rounded-full ${score >= 80 ? "bg-green-500" : score >= 60 ? "bg-yellow-500" : "bg-red-500"}`}
                      style={{ width: `${Math.min(100, score)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Strengths & Improvements */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 mb-6">
            {evaluation.strengths && evaluation.strengths.length > 0 && (
              <div className="rounded-lg border border-green-200 bg-green-50 p-4 dark:bg-green-950 dark:border-green-800">
                <h3 className="font-semibold text-green-800 dark:text-green-300 mb-2">{t("session", "strengths")}</h3>
                <ul className="space-y-1">
                  {evaluation.strengths.map((s, i) => (
                    <li key={i} className="text-sm text-green-700 dark:text-green-400">+ {s}</li>
                  ))}
                </ul>
              </div>
            )}
            {evaluation.improvements && evaluation.improvements.length > 0 && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:bg-amber-950 dark:border-amber-800">
                <h3 className="font-semibold text-amber-800 dark:text-amber-300 mb-2">{t("session", "areasToImprove")}</h3>
                <ul className="space-y-1">
                  {evaluation.improvements.map((s, i) => (
                    <li key={i} className="text-sm text-amber-700 dark:text-amber-400">- {s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Detailed Feedback */}
          {evaluation.detailed_feedback && (
            <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800 mb-6">
              <h3 className="font-semibold text-gray-900 dark:text-white mb-2">{t("session", "detailedFeedback")}</h3>
              <p className="text-sm text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                {evaluation.detailed_feedback}
              </p>
            </div>
          )}

          {/* Transcript */}
          <div className="rounded-lg border border-gray-200 bg-white p-6 dark:bg-gray-900 dark:border-gray-800">
            <h3 className="font-semibold text-gray-900 dark:text-white mb-4">{t("session", "dialogTranscript")}</h3>
            <div className="space-y-3 max-h-96 overflow-y-auto">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[75%] rounded-lg px-4 py-2 text-sm ${
                      msg.role === "user"
                        ? "bg-brand-600 text-white"
                        : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Chat view
  return (
    <div className="flex flex-col h-screen">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800 flex-shrink-0">
        <div className="mx-auto max-w-4xl px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-base font-semibold text-gray-900 dark:text-white">
                {session?.scenario?.title || t("session", "title")}
              </h1>
              <p className="text-xs text-gray-500">
                {t("training", "client")} {clientName}
                {session?.scenario?.client_persona?.mood && ` | ${t("session", "mood")} ${session.scenario.client_persona.mood}`}
                {useWS && (
                  <span className="ml-2 inline-flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-green-500 animate-pulse" />
                    <span className="text-green-600 dark:text-green-400">{t("session", "live")}</span>
                  </span>
                )}
              </p>
            </div>
            <div className="flex gap-2">
              {isActive && messages.length > 0 && (
                <button
                  onClick={completeSession}
                  disabled={completing}
                  className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-green-500 transition-colors disabled:opacity-50"
                >
                  {completing ? t("session", "evaluating") : t("session", "completeEvaluate")}
                </button>
              )}
              <Link
                href="/training"
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300"
              >
                {t("common", "back")}
              </Link>
            </div>
          </div>
        </div>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-4xl px-4 py-4 sm:px-6 lg:px-8">
          {error && (
            <div className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {messages.length === 0 && isActive && (
            <div className="text-center py-12">
              <p className="text-gray-500 mb-2">{t("session", "startConversation", { name: clientName })}</p>
              <p className="text-sm text-gray-400">
                {session?.scenario?.description || t("session", "typeFirstMessage")}
              </p>
            </div>
          )}

          <div className="space-y-3">
            {messages.map((msg, idx) => (
              <div
                key={msg.id || `msg-${idx}`}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[75%] rounded-lg px-4 py-2 text-sm ${
                    msg.role === "user"
                      ? "bg-brand-600 text-white"
                      : "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-100"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <p className="text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{clientName}</p>
                  )}
                  <p className="whitespace-pre-wrap">{msg.content}</p>
                </div>
              </div>
            ))}
            {(sending || ws.isWaitingResponse) && (
              <div className="flex justify-start">
                <div className="bg-gray-100 dark:bg-gray-800 rounded-lg px-4 py-2 text-sm text-gray-500">
                  {t("session", "isTyping", { name: clientName })}
                </div>
              </div>
            )}
          </div>
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input */}
      {isActive && (
        <div className="border-t border-gray-200 bg-white dark:bg-gray-900 dark:border-gray-800 flex-shrink-0">
          <div className="mx-auto max-w-4xl px-4 py-3 sm:px-6 lg:px-8">
            <div className="flex gap-2">
              <textarea
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={t("session", "placeholder")}
                rows={1}
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 dark:bg-gray-800 dark:border-gray-600 dark:text-white resize-none"
                disabled={sending || ws.isWaitingResponse}
              />
              <button
                onClick={sendMessage}
                disabled={sending || ws.isWaitingResponse || !inputText.trim()}
                className="rounded-md bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {t("common", "send")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
