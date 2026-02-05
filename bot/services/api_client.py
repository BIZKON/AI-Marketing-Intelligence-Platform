"""HTTP client for communicating with the FastAPI backend from the Telegram bot."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=API_BASE_URL, timeout=30.0)
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


class APIClient:
    """Wrapper around backend API calls for the Telegram bot."""

    def __init__(self, token: str | None = None) -> None:
        self.token = token

    @property
    def _headers(self) -> dict[str, str]:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    async def _request(
        self, method: str, path: str, json: dict | None = None, params: dict | None = None
    ) -> dict | list | None:
        client = await get_client()
        try:
            resp = await client.request(method, path, json=json, params=params, headers=self._headers)
            if resp.status_code == 204:
                return None
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("API error %s %s: %s %s", method, path, e.response.status_code, e.response.text)
            raise
        except httpx.RequestError as e:
            logger.error("API connection error %s %s: %s", method, path, e)
            raise

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def auth_telegram(
        self, telegram_id: int, username: str | None = None, full_name: str | None = None
    ) -> dict:
        data = await self._request("POST", "/auth/telegram", json={
            "telegram_id": telegram_id,
            "username": username,
            "full_name": full_name,
        })
        self.token = data["access_token"]
        return data

    # ── User Profile ─────────────────────────────────────────────────────────

    async def get_me(self) -> dict:
        return await self._request("GET", "/users/me")

    async def update_profile(self, **kwargs: Any) -> dict:
        return await self._request("PATCH", "/users/me", json=kwargs)

    # ── Billing ──────────────────────────────────────────────────────────────

    async def get_subscription(self) -> dict | None:
        return await self._request("GET", "/billing/subscription")

    async def create_checkout(self, plan: str) -> dict:
        return await self._request("POST", "/billing/checkout", json={"plan": plan})

    async def create_portal(self) -> dict:
        return await self._request("POST", "/billing/portal")

    # ── Competitors ──────────────────────────────────────────────────────────

    async def list_competitors(self) -> list[dict]:
        return await self._request("GET", "/competitors/")

    async def create_competitor(
        self, name: str, url: str | None = None, platforms: list[str] | None = None
    ) -> dict:
        return await self._request("POST", "/competitors/", json={
            "name": name,
            "url": url,
            "platforms": platforms or [],
        })

    async def delete_competitor(self, competitor_id: str) -> None:
        await self._request("DELETE", f"/competitors/{competitor_id}")

    # ── Reports ──────────────────────────────────────────────────────────────

    async def list_reports(self, report_type: str | None = None, limit: int = 5) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if report_type:
            params["report_type"] = report_type
        return await self._request("GET", "/reports/", params=params)

    async def request_digest(self, competitor_ids: list[str] | None = None) -> dict:
        return await self._request("POST", "/reports/digest", json={"competitor_ids": competitor_ids})

    # ── Content ──────────────────────────────────────────────────────────────

    async def list_plans(self) -> list[dict]:
        return await self._request("GET", "/content/plans")

    async def create_plan(self, period: str = "weekly") -> dict:
        return await self._request("POST", "/content/plans", json={"period": period})

    async def list_tasks(self, task_status: str | None = None) -> list[dict]:
        params = {}
        if task_status:
            params["task_status"] = task_status
        return await self._request("GET", "/content/tasks", params=params)

    async def approve_task(self, task_id: str) -> dict:
        return await self._request("POST", f"/content/tasks/{task_id}/approve")

    # ── Usage ────────────────────────────────────────────────────────────────

    async def get_usage_summary(self) -> dict:
        return await self._request("GET", "/competitors/usage/summary")
