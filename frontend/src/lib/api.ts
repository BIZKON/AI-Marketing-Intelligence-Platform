const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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

async function apiFetch<T>(endpoint: string, options: FetchOptions = {}): Promise<T> {
  const { token, headers, ...rest } = options;

  const res = await fetch(`${API_BASE}${endpoint}`, {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers,
    },
    ...rest,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(res.status, error.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Auth
  login: (email: string, password: string) =>
    apiFetch<AuthResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, fullName?: string) =>
    apiFetch<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    }),

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
};
