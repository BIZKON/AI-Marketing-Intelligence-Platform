const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface FetchOptions extends RequestInit {
  token?: string;
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
    throw new Error(error.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export const api = {
  // Auth
  login: (email: string, password: string) =>
    apiFetch<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string, fullName?: string) =>
    apiFetch<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    }),

  // Users
  getMe: (token: string) =>
    apiFetch("/users/me", { token }),

  // Competitors
  getCompetitors: (token: string) =>
    apiFetch("/competitors/", { token }),

  createCompetitor: (token: string, data: { name: string; url?: string; platforms?: string[] }) =>
    apiFetch("/competitors/", { token, method: "POST", body: JSON.stringify(data) }),

  // Reports
  getReports: (token: string, type?: string) =>
    apiFetch(`/reports/${type ? `?report_type=${type}` : ""}`, { token }),

  requestDigest: (token: string) =>
    apiFetch("/reports/digest", { token, method: "POST", body: JSON.stringify({}) }),

  // Content
  getPlans: (token: string) =>
    apiFetch("/content/plans", { token }),

  getTasks: (token: string) =>
    apiFetch("/content/tasks", { token }),

  // Billing
  getSubscription: (token: string) =>
    apiFetch("/billing/subscription", { token }),

  createCheckout: (token: string, plan: string) =>
    apiFetch<{ checkout_url: string }>("/billing/checkout", {
      token,
      method: "POST",
      body: JSON.stringify({ plan }),
    }),
};
