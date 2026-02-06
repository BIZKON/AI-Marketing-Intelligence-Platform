"""Real call analysis service — upload, transcribe, and evaluate real sales calls.

Uses Atlas Cloud for transcription (Whisper) and evaluation (LLM).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.voice_service import VoiceService
from app.services.training_service import TrainingService
from app.models.training_session import SessionMode, SessionStatus, TrainingSession
from app.models.session_message import SessionMessage

logger = logging.getLogger(__name__)


class CallAnalysisService:
    """Analyze real sales call recordings via Atlas Cloud."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.voice_service = VoiceService()
        self.training_service = TrainingService(db)

    async def analyze_call(
        self,
        user_id: uuid.UUID,
        audio_data: bytes,
        filename: str = "call.mp3",
        scenario_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """Full pipeline: transcribe → detect speakers → evaluate."""
        # 1. Transcribe via Atlas Cloud
        result = await self.voice_service.transcribe_audio(audio_data, filename)
        if result.get("error"):
            return {"error": result["error"]}

        transcript_text = result.get("text", "")
        segments = result.get("segments", [])

        # 2. Detect speakers
        speaker_segments = self.voice_service.detect_speakers(segments)
        formatted_transcript = self.voice_service.format_transcript(speaker_segments)

        # 3. Create a training session for the analysis
        session = TrainingSession(
            user_id=user_id, scenario_id=scenario_id,
            mode=SessionMode.REAL_CALL_ANALYSIS, status=SessionStatus.IN_PROGRESS,
        )
        self.db.add(session)
        await self.db.flush()

        # 4. Store transcript as messages
        current_speaker = None
        current_text = []
        for seg in speaker_segments:
            speaker = seg.get("speaker", "Unknown")
            text = seg.get("text", "").strip()
            if not text:
                continue
            if speaker != current_speaker:
                if current_speaker and current_text:
                    role = "user" if current_speaker == "Admin" else "assistant"
                    msg = SessionMessage(
                        session_id=session.id, role=role, content=" ".join(current_text),
                    )
                    self.db.add(msg)
                current_speaker = speaker
                current_text = [text]
            else:
                current_text.append(text)

        if current_speaker and current_text:
            role = "user" if current_speaker == "Admin" else "assistant"
            msg = SessionMessage(session_id=session.id, role=role, content=" ".join(current_text))
            self.db.add(msg)

        await self.db.flush()

        # 5. Complete and evaluate
        session.status = SessionStatus.COMPLETED
        await self.db.flush()

        session = await self.training_service.get_session(session.id)
        evaluation = await self.training_service.evaluate_session(session)

        return {
            "session_id": str(session.id),
            "transcript": formatted_transcript,
            "speakers": [
                {"speaker": s.get("speaker"), "text": s.get("text", ""),
                 "start": s.get("start"), "end": s.get("end")}
                for s in speaker_segments
            ],
            "evaluation": {
                "overall_score": evaluation.overall_score,
                "criteria_scores": evaluation.criteria_scores,
                "strengths": evaluation.strengths,
                "improvements": evaluation.improvements,
                "detailed_feedback": evaluation.detailed_feedback,
                "mood_analysis": evaluation.mood_analysis,
            },
        }
