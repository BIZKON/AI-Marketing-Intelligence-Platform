"""Pydantic schemas for the training module API."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


# ── Scenario Schemas ──────────────────────────────────────────────────────────


class ClientPersona(BaseModel):
    name: str
    age: int | None = None
    mood: str | None = None
    background: str | None = None
    objections: list[str] = []


class ScenarioCreate(BaseModel):
    title: str = Field(..., max_length=500)
    description: str | None = None
    type: str  # incoming_call, outbound_call, partner_pitch, objection_handling, closing
    difficulty: str = "medium"  # easy, medium, hard
    client_persona: ClientPersona
    system_prompt: str
    ideal_script: str | None = None
    success_criteria: dict[str, Any] | None = None
    tags: list[str] | None = None


class ScenarioResponse(BaseModel):
    id: uuid.UUID
    title: str
    description: str | None = None
    type: str
    difficulty: str
    client_persona: dict[str, Any]
    system_prompt: str
    ideal_script: str | None = None
    success_criteria: dict[str, Any] | None = None
    is_public: bool
    tags: list[str] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Session Schemas ───────────────────────────────────────────────────────────


class SessionCreate(BaseModel):
    scenario_id: uuid.UUID
    mode: str = "text"  # text, voice, real_call_analysis


class SessionResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    scenario_id: uuid.UUID | None = None
    mode: str
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SessionDetailResponse(SessionResponse):
    messages: list["MessageResponse"] = []
    evaluation: "EvaluationResponse | None" = None
    scenario: ScenarioResponse | None = None


# ── Message Schemas ───────────────────────────────────────────────────────────


class SendMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class SimulateClientResponse(BaseModel):
    user_message: MessageResponse
    assistant_message: MessageResponse


# ── Evaluation Schemas ────────────────────────────────────────────────────────


class CriteriaScores(BaseModel):
    greeting: int = Field(0, ge=0, le=100)
    listening: int = Field(0, ge=0, le=100)
    objection_handling: int = Field(0, ge=0, le=100)
    product_knowledge: int = Field(0, ge=0, le=100)
    closing: int = Field(0, ge=0, le=100)
    tone_empathy: int = Field(0, ge=0, le=100)
    script_adherence: int = Field(0, ge=0, le=100)


class EvaluationResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    overall_score: int | None = None
    criteria_scores: dict[str, Any]
    strengths: list[str] | None = None
    improvements: list[str] | None = None
    detailed_feedback: str | None = None
    mood_analysis: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Achievement Schemas ───────────────────────────────────────────────────────


class AchievementResponse(BaseModel):
    id: uuid.UUID
    achievement_type: str
    metadata_json: dict[str, Any] | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Analytics Schemas ─────────────────────────────────────────────────────────


class WeeklyStatsResponse(BaseModel):
    week_start: date
    sessions_count: int
    avg_score: float | None = None
    total_duration_minutes: int

    model_config = {"from_attributes": True}


class TrainingAnalytics(BaseModel):
    total_sessions: int
    completed_sessions: int
    avg_score: float | None = None
    best_score: int | None = None
    total_duration_minutes: int
    weekly_stats: list[WeeklyStatsResponse] = []
    criteria_averages: dict[str, float] = {}
    recent_sessions: list[SessionResponse] = []
    achievements: list[AchievementResponse] = []
