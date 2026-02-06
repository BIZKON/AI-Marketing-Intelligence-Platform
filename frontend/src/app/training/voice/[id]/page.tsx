"use client";

import { useEffect, useRef, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";

export default function VoiceSessionPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const [status, setStatus] = useState<"idle" | "recording" | "processing" | "done">("idle");
  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        stream.getTracks().forEach((t) => t.stop());
        await sendAudio(blob);
      };

      mediaRecorder.start();
      setStatus("recording");
    } catch {
      setError("Microphone access denied");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && status === "recording") {
      mediaRecorderRef.current.stop();
      setStatus("processing");
    }
  };

  const sendAudio = async (blob: Blob) => {
    const token = getToken();
    if (!token) return;

    try {
      const formData = new FormData();
      formData.append("file", blob, "recording.webm");

      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || "/api/v1"}/voice/transcribe`,
        {
          method: "POST",
          headers: { Authorization: `Bearer ${token}` },
          body: formData,
        }
      );
      const data = await res.json();
      const transcript = data.transcript || "";

      if (transcript) {
        setMessages((prev) => [...prev, { role: "user", content: transcript }]);

        // Send as text message to training session
        const result = await api.sendTrainingMessage(token, sessionId, transcript);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: result.assistant_message.content },
        ]);
      }
      setStatus("idle");
    } catch {
      setError("Failed to process audio");
      setStatus("idle");
    }
  };

  const handleComplete = async () => {
    const token = getToken();
    if (!token) return;
    setStatus("done");
    try {
      await api.completeTrainingSession(token, sessionId);
      router.push(`/training/session/${sessionId}`);
    } catch {
      setError("Failed to complete session");
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 p-6">
      <div className="max-w-2xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Voice Training Session
          </h1>
          <button
            onClick={handleComplete}
            disabled={status === "done" || messages.length === 0}
            className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
          >
            Complete Session
          </button>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-100 text-red-700 rounded-lg">{error}</div>
        )}

        {/* Messages */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow p-4 mb-6 space-y-3 min-h-[300px] max-h-[500px] overflow-y-auto">
          {messages.length === 0 && (
            <p className="text-gray-400 text-center py-10">
              Press the microphone button to start speaking
            </p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[80%] px-4 py-2 rounded-2xl text-sm ${
                  msg.role === "user"
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white"
                }`}
              >
                {msg.content}
              </div>
            </div>
          ))}
        </div>

        {/* Recording controls */}
        <div className="flex justify-center">
          {status === "idle" && (
            <button
              onClick={startRecording}
              className="w-20 h-20 rounded-full bg-red-500 hover:bg-red-600 text-white flex items-center justify-center shadow-lg transition-all"
            >
              <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
              </svg>
            </button>
          )}
          {status === "recording" && (
            <button
              onClick={stopRecording}
              className="w-20 h-20 rounded-full bg-red-600 hover:bg-red-700 text-white flex items-center justify-center shadow-lg animate-pulse"
            >
              <svg className="w-8 h-8" fill="currentColor" viewBox="0 0 24 24">
                <rect x="6" y="6" width="12" height="12" rx="2" />
              </svg>
            </button>
          )}
          {status === "processing" && (
            <div className="w-20 h-20 rounded-full bg-gray-300 flex items-center justify-center">
              <svg className="w-8 h-8 animate-spin text-gray-600" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            </div>
          )}
        </div>

        <p className="text-center text-sm text-gray-500 mt-4">
          {status === "idle" && "Tap to start recording"}
          {status === "recording" && "Recording... Tap to stop"}
          {status === "processing" && "Processing audio..."}
          {status === "done" && "Session completed"}
        </p>
      </div>
    </div>
  );
}
