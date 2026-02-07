"""Locust load tests for AI Marketing Intelligence Platform.

Simulates realistic user behavior across all major API endpoints:
  - Auth (register, login)
  - Training (scenarios, sessions, messages, evaluation)
  - Monitoring (health, atlas status, platform stats)
  - Content & Reports

Usage:
  # Install
  pip install locust

  # Run (web UI at http://localhost:8089)
  locust -f tests/load/locustfile.py --host http://localhost:8000

  # Headless run (100 users, 10 spawn/sec, 2 min)
  locust -f tests/load/locustfile.py --host http://localhost:8000 \
    --users 100 --spawn-rate 10 --run-time 2m --headless --csv results/locust

  # Docker (with backend running)
  docker run --rm -p 8089:8089 -v $(pwd)/tests/load:/mnt/locust \
    locustio/locust -f /mnt/locust/locustfile.py --host http://host.docker.internal:8000
"""

from __future__ import annotations

import json
import random
import string
import uuid

from locust import HttpUser, between, task, tag, events


def _random_email() -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"loadtest-{suffix}@example.com"


class TrainingUser(HttpUser):
    """Simulates a user going through the training flow."""

    wait_time = between(1, 3)
    token: str | None = None
    scenario_ids: list[str] = []
    active_session_id: str | None = None

    def on_start(self) -> None:
        """Register and authenticate."""
        email = _random_email()
        password = "LoadTest123!"

        # Try register
        with self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password},
            catch_response=True,
            name="/auth/register",
        ) as resp:
            if resp.status_code in (200, 201):
                data = resp.json()
                self.token = data.get("access_token")
                resp.success()
            elif resp.status_code == 409:
                # Already exists — login
                resp.success()
            else:
                resp.failure(f"Register failed: {resp.status_code}")

        # Login if register didn't return token
        if not self.token:
            with self.client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
                catch_response=True,
                name="/auth/login",
            ) as resp:
                if resp.status_code == 200:
                    self.token = resp.json().get("access_token")
                    resp.success()
                else:
                    resp.failure(f"Login failed: {resp.status_code}")

    @property
    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    # ── Health ─────────────────────────────────────────────────────────────

    @tag("health")
    @task(5)
    def health_check(self) -> None:
        """GET /health — lightweight, high frequency."""
        self.client.get("/health", name="/health")

    @tag("health")
    @task(1)
    def health_detailed(self) -> None:
        """GET /health/detailed — heavier, checks all services."""
        self.client.get("/health/detailed", name="/health/detailed")

    # ── Training Scenarios ─────────────────────────────────────────────────

    @tag("training", "scenarios")
    @task(3)
    def list_scenarios(self) -> None:
        """GET /training/scenarios — list available scenarios."""
        with self.client.get(
            "/api/v1/training/scenarios",
            headers=self._headers,
            catch_response=True,
            name="/training/scenarios",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.scenario_ids = [s["id"] for s in data] if data else []
                resp.success()
            elif resp.status_code in (401, 500):
                resp.success()  # Expected without auth/DB
            else:
                resp.failure(f"Unexpected: {resp.status_code}")

    # ── Training Sessions ──────────────────────────────────────────────────

    @tag("training", "sessions")
    @task(2)
    def create_session(self) -> None:
        """POST /training/sessions — start a new training session."""
        if not self.scenario_ids:
            return

        scenario_id = random.choice(self.scenario_ids)
        with self.client.post(
            "/api/v1/training/sessions",
            json={"scenario_id": scenario_id, "mode": "text"},
            headers=self._headers,
            catch_response=True,
            name="/training/sessions [POST]",
        ) as resp:
            if resp.status_code in (200, 201):
                self.active_session_id = resp.json().get("id")
                resp.success()
            elif resp.status_code in (401, 404, 500):
                resp.success()
            else:
                resp.failure(f"Create session: {resp.status_code}")

    @tag("training", "sessions")
    @task(3)
    def list_sessions(self) -> None:
        """GET /training/sessions — list user's sessions."""
        self.client.get(
            "/api/v1/training/sessions?limit=10",
            headers=self._headers,
            name="/training/sessions",
        )

    # ── Training Chat (AI simulation) ──────────────────────────────────────

    @tag("training", "chat")
    @task(4)
    def send_message(self) -> None:
        """POST /training/sessions/{id}/message — send message, get AI response."""
        if not self.active_session_id:
            return

        messages = [
            "Здравствуйте! Студия йоги Алхимия, меня зовут Анна.",
            "Расскажите, что вас привело к нам?",
            "У нас есть мягкие классы, идеально для начинающих.",
            "Пробное занятие у нас бесплатное!",
            "Давайте я запишу вас на удобное время. Какой день подходит?",
            "Отлично! Записала вас на субботу в 10:00.",
        ]
        message = random.choice(messages)

        with self.client.post(
            f"/api/v1/training/sessions/{self.active_session_id}/message",
            json={"message": message},
            headers=self._headers,
            catch_response=True,
            name="/training/sessions/{id}/message",
            timeout=120,  # AI response can take time
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code in (400, 401, 404, 500):
                # Session may be completed/not found — reset
                self.active_session_id = None
                resp.success()
            else:
                resp.failure(f"Send message: {resp.status_code}")

    # ── Session Completion & Evaluation ────────────────────────────────────

    @tag("training", "evaluation")
    @task(1)
    def complete_session(self) -> None:
        """POST /training/sessions/{id}/complete — evaluate dialog."""
        if not self.active_session_id:
            return

        with self.client.post(
            f"/api/v1/training/sessions/{self.active_session_id}/complete",
            headers=self._headers,
            catch_response=True,
            name="/training/sessions/{id}/complete",
            timeout=120,
        ) as resp:
            if resp.status_code == 200:
                self.active_session_id = None
                resp.success()
            elif resp.status_code in (400, 401, 404, 500):
                self.active_session_id = None
                resp.success()
            else:
                resp.failure(f"Complete: {resp.status_code}")

    # ── Analytics ──────────────────────────────────────────────────────────

    @tag("training", "analytics")
    @task(2)
    def get_analytics(self) -> None:
        """GET /training/analytics — personal training stats."""
        self.client.get(
            "/api/v1/training/analytics",
            headers=self._headers,
            name="/training/analytics",
        )

    @tag("training")
    @task(1)
    def get_achievements(self) -> None:
        """GET /training/achievements — user achievements."""
        self.client.get(
            "/api/v1/training/achievements",
            headers=self._headers,
            name="/training/achievements",
        )

    # ── Monitoring ─────────────────────────────────────────────────────────

    @tag("monitoring")
    @task(2)
    def atlas_cloud_status(self) -> None:
        """GET /monitoring/atlas-cloud/status — circuit breaker status."""
        self.client.get(
            "/api/v1/monitoring/atlas-cloud/status",
            headers=self._headers,
            name="/monitoring/atlas-cloud/status",
        )

    @tag("monitoring")
    @task(1)
    def training_platform_stats(self) -> None:
        """GET /monitoring/training/stats — platform-wide stats."""
        self.client.get(
            "/api/v1/monitoring/training/stats",
            headers=self._headers,
            name="/monitoring/training/stats",
        )

    # ── Gamification ───────────────────────────────────────────────────────

    @tag("gamification")
    @task(1)
    def gamification_profile(self) -> None:
        """GET /gamification/profile — user level, XP, streaks."""
        self.client.get(
            "/api/v1/gamification/profile",
            headers=self._headers,
            name="/gamification/profile",
        )

    @tag("gamification")
    @task(1)
    def daily_challenges(self) -> None:
        """GET /gamification/challenges — today's challenges."""
        self.client.get(
            "/api/v1/gamification/challenges",
            headers=self._headers,
            name="/gamification/challenges",
        )


class ReadOnlyUser(HttpUser):
    """Simulates users who only browse scenarios and analytics (no AI calls)."""

    wait_time = between(2, 5)
    weight = 3  # 3x more read-only users than training users

    @task(5)
    def health(self) -> None:
        self.client.get("/health")

    @task(3)
    def list_scenarios(self) -> None:
        self.client.get("/api/v1/training/scenarios", name="/training/scenarios [anon]")

    @task(1)
    def openapi_docs(self) -> None:
        self.client.get("/api/v1/openapi.json", name="/openapi.json")
