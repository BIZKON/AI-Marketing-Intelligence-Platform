const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface FetchOptions extends RequestInit {
  token?: string;
}

// Response types
export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  is_new_user: boolean;
  user: UserResponse;
}

export interface UserResponse {
  id: string;
  email: string;
  full_name: string | null;
  telegram_id: number | null;
  brand_name: string | null;
  brand_industry: string | null;
  brand_description: string | null;
  tone_of_voice: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface CompetitorResponse {
  id: string;
  name: string;
  url: string | null;
  platforms: string[];
  created_at: string;
  updated_at: string | null;
}

export interface ReportResponse {
  id: string;
  report_type: string;
  status: string;
  summary: string | null;
  created_at: string;
}

export interface ContentPlanResponse {
  id: string;
  period: string;
  status: string;
  created_at: string;
}

export interface ContentTaskResponse {
  id: string;
  content_type: string;
  status: string;
  title: string | null;
  draft_text: string | null;
  created_at: string;
}

export interface SubscriptionResponse {
  plan: string;
  status: string;
  current_period_end: string | null;
}

export interface CheckoutResponse {
  checkout_url: string;
}

// Training types
export interface TrainingScenarioResponse {
  id: string;
  title: string;
  description: string | null;
  type: string;
  difficulty: string;
  client_persona: {
    name: string;
    age?: number;
    mood?: string;
    background?: string;
    objections?: string[];
  };
  is_public: boolean;
  tags: string[] | null;
  created_at: string;
}

export interface TrainingSessionResponse {
  id: string;
  user_id: string;
  scenario_id: string | null;
  mode: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  created_at: string;
}

export interface TrainingMessageResponse {
  id: string;
  session_id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface TrainingEvaluationResponse {
  id: string;
  session_id: string;
  overall_score: number | null;
  criteria_scores: Record<string, number>;
  strengths: string[] | null;
  improvements: string[] | null;
  detailed_feedback: string | null;
  mood_analysis: string | null;
  created_at: string;
}

export interface SimulateClientResponse {
  user_message: TrainingMessageResponse;
  assistant_message: TrainingMessageResponse;
}

export interface TrainingSessionDetailResponse extends TrainingSessionResponse {
  messages: TrainingMessageResponse[];
  evaluation: TrainingEvaluationResponse | null;
  scenario: TrainingScenarioResponse | null;
}

export interface TrainingAchievementResponse {
  id: string;
  achievement_type: string;
  metadata_json: Record<string, string> | null;
  created_at: string;
}

export interface TrainingAnalyticsResponse {
  total_sessions: number;
  completed_sessions: number;
  avg_score: number | null;
  best_score: number | null;
  total_duration_minutes: number;
  weekly_stats: { week_start: string; sessions_count: number; avg_score: number | null; total_duration_minutes: number }[];
  criteria_averages: Record<string, number>;
  recent_sessions: TrainingSessionResponse[];
  achievements: TrainingAchievementResponse[];
}

// Token management helpers (#057)
function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}

function setTokens(access: string, refresh: string): void {
  localStorage.setItem("token", access);
  localStorage.setItem("refresh_token", refresh);
}

function clearTokens(): void {
  localStorage.removeItem("token");
  localStorage.removeItem("refresh_token");
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  try {
    const res = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
    });
    if (!res.ok) {
      clearTokens();
      return null;
    }
    const data = await res.json();
    setTokens(data.access_token, data.refresh_token || refresh);
    return data.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

const REQUEST_TIMEOUT_MS = 30_000;

async function apiFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { token, headers, signal, ...rest } = options;

  // Timeout support (#057)
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  const mergedSignal = signal || controller.signal;

  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
      signal: mergedSignal,
      ...rest,
    });

    // Auto-refresh on 401 (#057)
    if (res.status === 401 && token) {
      const newToken = await refreshAccessToken();
      if (newToken) {
        const retryRes = await fetch(`${API_BASE}${endpoint}`, {
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${newToken}`,
            ...headers,
          },
          ...rest,
        });
        if (!retryRes.ok) {
          const error = await retryRes.json().catch(() => ({ detail: "Unknown error" }));
          throw new ApiError(retryRes.status, error.detail || `HTTP ${retryRes.status}`);
        }
        return retryRes.json();
      }
    }

    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: "Unknown error" }));
      throw new ApiError(res.status, error.detail || `HTTP ${res.status}`);
    }

    return res.json();
  } finally {
    clearTimeout(timeout);
  }
}

export { getToken, setTokens, clearTokens };

export const api = {
  // Auth
  login: async (email: string, password: string) => {
    const resp = await apiFetch<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (resp.access_token) {
      setTokens(resp.access_token, resp.refresh_token || "");
    }
    return resp;
  },

  register: async (email: string, password: string, fullName?: string) => {
    const resp = await apiFetch<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    if (resp.access_token) {
      setTokens(resp.access_token, resp.refresh_token || "");
    }
    return resp;
  },

  // Users
  getMe: (token: string) =>
    apiFetch<UserResponse>("/users/me", { token }),

  // Competitors
  getCompetitors: (token: string) =>
    apiFetch<CompetitorResponse[]>("/competitors/", { token }),

  createCompetitor: (token: string, data: { name: string; url?: string; platforms?: string[] }) =>
    apiFetch<CompetitorResponse>("/competitors/", { token, method: "POST", body: JSON.stringify(data) }),

  // Reports
  getReports: (token: string, type?: string) =>
    apiFetch<ReportResponse[]>(`/reports/${type ? `?report_type=${type}` : ""}`, { token }),

  requestDigest: (token: string) =>
    apiFetch<ReportResponse>("/reports/digest", { token, method: "POST", body: JSON.stringify({}) }),

  // Content
  getPlans: (token: string) =>
    apiFetch<ContentPlanResponse[]>("/content/plans", { token }),

  getTasks: (token: string) =>
    apiFetch<ContentTaskResponse[]>("/content/tasks", { token }),

  // Billing
  getSubscription: (token: string) =>
    apiFetch<SubscriptionResponse>("/billing/subscription", { token }),

  createCheckout: (token: string, plan: string) =>
    apiFetch<CheckoutResponse>("/billing/checkout", {
      token,
      method: "POST",
      body: JSON.stringify({ plan }),
    }),

  // Training
  getScenarios: (token: string) =>
    apiFetch<TrainingScenarioResponse[]>("/training/scenarios", { token }),

  createTrainingSession: (token: string, scenarioId: string, mode: string = "text") =>
    apiFetch<TrainingSessionResponse>("/training/sessions", {
      token,
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId, mode }),
    }),

  getTrainingSessions: (token: string, limit: number = 20) =>
    apiFetch<TrainingSessionResponse[]>(`/training/sessions?limit=${limit}`, { token }),

  getTrainingSession: (token: string, sessionId: string) =>
    apiFetch<TrainingSessionDetailResponse>(`/training/sessions/${sessionId}`, { token }),

  sendTrainingMessage: (token: string, sessionId: string, message: string) =>
    apiFetch<SimulateClientResponse>(`/training/sessions/${sessionId}/message`, {
      token,
      method: "POST",
      body: JSON.stringify({ message }),
    }),

  completeTrainingSession: (token: string, sessionId: string) =>
    apiFetch<TrainingEvaluationResponse>(`/training/sessions/${sessionId}/complete`, {
      token,
      method: "POST",
    }),

  getTrainingAnalytics: (token: string) =>
    apiFetch<TrainingAnalyticsResponse>("/training/analytics", { token }),

  getTrainingAchievements: (token: string) =>
    apiFetch<TrainingAchievementResponse[]>("/training/achievements", { token }),
};
