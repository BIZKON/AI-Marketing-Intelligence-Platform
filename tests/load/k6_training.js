/**
 * k6 performance tests for AI Marketing Intelligence Platform.
 *
 * Tests critical API paths with defined SLOs:
 *   - Health checks: p95 < 50ms
 *   - Auth endpoints: p95 < 500ms
 *   - Training CRUD: p95 < 1s
 *   - AI simulation (chat): p95 < 30s (LLM latency)
 *   - AI evaluation: p95 < 60s
 *
 * Usage:
 *   # Install k6: https://k6.io/docs/get-started/installation/
 *
 *   # Quick smoke test (1 user, 30s)
 *   k6 run tests/load/k6_training.js
 *
 *   # Load test (50 users, 5 min)
 *   k6 run tests/load/k6_training.js --env USERS=50 --env DURATION=5m
 *
 *   # Stress test (ramp up to 200 users)
 *   k6 run tests/load/k6_training.js --env SCENARIO=stress
 *
 *   # With custom API URL
 *   k6 run tests/load/k6_training.js --env BASE_URL=https://api.example.com
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

// ── Config ────────────────────────────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API = `${BASE_URL}/api/v1`;

// Custom metrics
const errorRate = new Rate("errors");
const healthLatency = new Trend("health_latency", true);
const authLatency = new Trend("auth_latency", true);
const trainingCrudLatency = new Trend("training_crud_latency", true);
const aiChatLatency = new Trend("ai_chat_latency", true);
const aiEvalLatency = new Trend("ai_eval_latency", true);

// ── Scenarios ─────────────────────────────────────────────────────────────────

const scenarios = {
  // Default: constant load
  default: {
    executor: "constant-vus",
    vus: parseInt(__ENV.USERS || "5"),
    duration: __ENV.DURATION || "1m",
  },
  // Stress: ramp up
  stress: {
    executor: "ramping-vus",
    startVUs: 0,
    stages: [
      { duration: "1m", target: 20 },
      { duration: "3m", target: 100 },
      { duration: "2m", target: 200 },
      { duration: "1m", target: 200 },
      { duration: "2m", target: 0 },
    ],
  },
  // Spike
  spike: {
    executor: "ramping-vus",
    startVUs: 0,
    stages: [
      { duration: "30s", target: 10 },
      { duration: "10s", target: 300 },
      { duration: "1m", target: 300 },
      { duration: "30s", target: 10 },
      { duration: "30s", target: 0 },
    ],
  },
  // Soak: long running
  soak: {
    executor: "constant-vus",
    vus: 30,
    duration: "30m",
  },
};

const selectedScenario = __ENV.SCENARIO || "default";

export const options = {
  scenarios: {
    main: scenarios[selectedScenario] || scenarios.default,
  },
  thresholds: {
    // SLOs
    http_req_failed: ["rate<0.05"],          // <5% errors
    health_latency: ["p(95)<50"],            // Health: p95 < 50ms
    auth_latency: ["p(95)<500"],             // Auth: p95 < 500ms
    training_crud_latency: ["p(95)<1000"],   // CRUD: p95 < 1s
    ai_chat_latency: ["p(95)<30000"],        // AI chat: p95 < 30s
    ai_eval_latency: ["p(95)<60000"],        // AI eval: p95 < 60s
    errors: ["rate<0.1"],                    // <10% custom error rate
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function authHeaders(token) {
  return {
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  };
}

function randomString(len) {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let result = "";
  for (let i = 0; i < len; i++) {
    result += chars[Math.floor(Math.random() * chars.length)];
  }
  return result;
}

// ── Main Test ─────────────────────────────────────────────────────────────────

export default function () {
  let token = null;
  let scenarioIds = [];
  let sessionId = null;

  // ── Health ────────────────────────────────────────────────────────
  group("Health Checks", () => {
    const res = http.get(`${BASE_URL}/health`);
    healthLatency.add(res.timings.duration);
    check(res, {
      "health: status 200": (r) => r.status === 200,
      "health: body has ok": (r) => r.json("status") === "ok",
    });

    const detailed = http.get(`${BASE_URL}/health/detailed`);
    healthLatency.add(detailed.timings.duration);
    check(detailed, {
      "health/detailed: status 200": (r) => r.status === 200,
    });
  });

  sleep(0.5);

  // ── Auth ──────────────────────────────────────────────────────────
  group("Authentication", () => {
    const email = `k6-${randomString(8)}@loadtest.dev`;
    const password = "K6LoadTest123!";

    // Register
    const regRes = http.post(
      `${API}/auth/register`,
      JSON.stringify({ email, password }),
      { headers: { "Content-Type": "application/json" }, tags: { name: "auth_register" } },
    );
    authLatency.add(regRes.timings.duration);

    if (regRes.status === 200 || regRes.status === 201) {
      const body = regRes.json();
      token = body.access_token;
      check(regRes, {
        "register: got token": () => !!token,
      });
    } else {
      // Try login
      const loginRes = http.post(
        `${API}/auth/login`,
        JSON.stringify({ email, password }),
        { headers: { "Content-Type": "application/json" }, tags: { name: "auth_login" } },
      );
      authLatency.add(loginRes.timings.duration);
      if (loginRes.status === 200) {
        token = loginRes.json().access_token;
      }
    }

    if (!token) {
      errorRate.add(1);
      return;
    }
    errorRate.add(0);
  });

  if (!token) return;

  sleep(0.5);

  // ── Training Scenarios ────────────────────────────────────────────
  group("Training Scenarios", () => {
    const res = http.get(`${API}/training/scenarios`, authHeaders(token));
    trainingCrudLatency.add(res.timings.duration);

    const ok = check(res, {
      "scenarios: status 200": (r) => r.status === 200,
    });

    if (ok && res.status === 200) {
      const data = res.json();
      if (Array.isArray(data)) {
        scenarioIds = data.map((s) => s.id);
      }
    }
    errorRate.add(ok ? 0 : 1);
  });

  sleep(0.5);

  // ── Create Training Session ───────────────────────────────────────
  if (scenarioIds.length > 0) {
    group("Create Session", () => {
      const scenarioId = scenarioIds[Math.floor(Math.random() * scenarioIds.length)];
      const res = http.post(
        `${API}/training/sessions`,
        JSON.stringify({ scenario_id: scenarioId, mode: "text" }),
        authHeaders(token),
      );
      trainingCrudLatency.add(res.timings.duration);

      const ok = check(res, {
        "create session: status 201": (r) => r.status === 201 || r.status === 200,
      });

      if (ok && (res.status === 200 || res.status === 201)) {
        sessionId = res.json().id;
      }
      errorRate.add(ok ? 0 : 1);
    });
  }

  sleep(0.5);

  // ── Send Messages (AI Simulation) ─────────────────────────────────
  if (sessionId) {
    group("AI Chat Simulation", () => {
      const messages = [
        "Здравствуйте! Студия йоги Алхимия, чем могу помочь?",
        "Расскажите, что вас привело к нам?",
        "У нас есть мягкие классы для начинающих, идеально подойдут.",
      ];

      for (const msg of messages) {
        const res = http.post(
          `${API}/training/sessions/${sessionId}/message`,
          JSON.stringify({ message: msg }),
          Object.assign({}, authHeaders(token), { timeout: "120s" }),
        );
        aiChatLatency.add(res.timings.duration);

        const ok = check(res, {
          "chat: status 200": (r) => r.status === 200,
          "chat: has assistant_message": (r) =>
            r.status === 200 && r.json("assistant_message") !== undefined,
        });
        errorRate.add(ok ? 0 : 1);

        sleep(1);
      }
    });
  }

  sleep(0.5);

  // ── Complete & Evaluate ───────────────────────────────────────────
  if (sessionId) {
    group("AI Evaluation", () => {
      const res = http.post(
        `${API}/training/sessions/${sessionId}/complete`,
        null,
        Object.assign({}, authHeaders(token), { timeout: "120s" }),
      );
      aiEvalLatency.add(res.timings.duration);

      const ok = check(res, {
        "eval: status 200": (r) => r.status === 200,
        "eval: has overall_score": (r) =>
          r.status === 200 && r.json("overall_score") !== undefined,
      });
      errorRate.add(ok ? 0 : 1);
    });
  }

  sleep(0.5);

  // ── Analytics ─────────────────────────────────────────────────────
  group("Analytics & Monitoring", () => {
    const analytics = http.get(`${API}/training/analytics`, authHeaders(token));
    trainingCrudLatency.add(analytics.timings.duration);
    check(analytics, {
      "analytics: status 200": (r) => r.status === 200,
    });

    const achievements = http.get(`${API}/training/achievements`, authHeaders(token));
    trainingCrudLatency.add(achievements.timings.duration);

    const atlasStatus = http.get(
      `${API}/monitoring/atlas-cloud/status`,
      authHeaders(token),
    );
    trainingCrudLatency.add(atlasStatus.timings.duration);
    check(atlasStatus, {
      "atlas status: status 200": (r) => r.status === 200,
    });

    const platformStats = http.get(
      `${API}/monitoring/training/stats`,
      authHeaders(token),
    );
    trainingCrudLatency.add(platformStats.timings.duration);
  });

  sleep(1);
}
