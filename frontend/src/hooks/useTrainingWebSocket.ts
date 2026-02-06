"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TrainingMessageResponse, TrainingEvaluationResponse } from "@/lib/api";

const WS_BASE =
  (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1")
    .replace(/^http/, "ws")
    .replace(/\/api\/v1$/, "");

export type WSStatus = "connecting" | "connected" | "disconnected" | "error";

interface WSMessage {
  type: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

interface UseTrainingWebSocketReturn {
  status: WSStatus;
  sendMessage: (content: string) => void;
  complete: () => void;
  lastUserMessage: TrainingMessageResponse | null;
  lastAssistantMessage: TrainingMessageResponse | null;
  evaluation: TrainingEvaluationResponse | null;
  error: string | null;
  isWaitingResponse: boolean;
}

export function useTrainingWebSocket(
  sessionId: string,
  token: string | null,
  enabled: boolean = true,
): UseTrainingWebSocketReturn {
  const wsRef = useRef<WebSocket | null>(null);
  const [status, setStatus] = useState<WSStatus>("disconnected");
  const [lastUserMessage, setLastUserMessage] = useState<TrainingMessageResponse | null>(null);
  const [lastAssistantMessage, setLastAssistantMessage] = useState<TrainingMessageResponse | null>(null);
  const [evaluation, setEvaluation] = useState<TrainingEvaluationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isWaitingResponse, setIsWaitingResponse] = useState(false);

  // Connect
  useEffect(() => {
    if (!enabled || !token || !sessionId) return;

    const url = `${WS_BASE}/ws/training/${sessionId}?token=${encodeURIComponent(token)}`;
    setStatus("connecting");
    setError(null);

    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      // Wait for "connected" message from server
    };

    ws.onmessage = (event) => {
      try {
        const data: WSMessage = JSON.parse(event.data);

        switch (data.type) {
          case "connected":
            setStatus("connected");
            break;

          case "response":
            setLastUserMessage(data.user_message);
            setLastAssistantMessage(data.assistant_message);
            setIsWaitingResponse(false);
            break;

          case "evaluation":
            setEvaluation({
              id: "",
              session_id: sessionId,
              overall_score: data.evaluation.overall_score,
              criteria_scores: data.evaluation.criteria_scores,
              strengths: data.evaluation.strengths,
              improvements: data.evaluation.improvements,
              detailed_feedback: data.evaluation.detailed_feedback,
              mood_analysis: data.evaluation.mood_analysis,
              created_at: new Date().toISOString(),
            });
            setIsWaitingResponse(false);
            break;

          case "error":
            setError(data.detail || "Unknown error");
            setIsWaitingResponse(false);
            break;
        }
      } catch {
        setError("Failed to parse server message");
      }
    };

    ws.onerror = () => {
      setStatus("error");
      setError("WebSocket connection error");
      setIsWaitingResponse(false);
    };

    ws.onclose = (event) => {
      setStatus("disconnected");
      if (event.code !== 1000 && event.code !== 4001 && event.code !== 4002) {
        // Unexpected close
        setError(event.reason || "Connection closed");
      }
    };

    return () => {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close();
      }
      wsRef.current = null;
    };
  }, [sessionId, token, enabled]);

  const sendMessage = useCallback((content: string) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("WebSocket is not connected");
      return;
    }
    setIsWaitingResponse(true);
    setError(null);
    ws.send(JSON.stringify({ type: "message", content }));
  }, []);

  const complete = useCallback(() => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      setError("WebSocket is not connected");
      return;
    }
    setIsWaitingResponse(true);
    setError(null);
    ws.send(JSON.stringify({ type: "complete" }));
  }, []);

  return {
    status,
    sendMessage,
    complete,
    lastUserMessage,
    lastAssistantMessage,
    evaluation,
    error,
    isWaitingResponse,
  };
}
