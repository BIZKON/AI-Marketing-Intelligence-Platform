"""Voice mode API routes — OpenAI Realtime WebSocket config + Whisper."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.voice_service import VoiceService

router = APIRouter()


@router.get("/config")
async def get_voice_config(
    user: User = Depends(get_current_user),
) -> dict:
    """Get WebSocket config for OpenAI Realtime API voice sessions."""
    svc = VoiceService()
    return svc.get_realtime_config()


@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    """Transcribe an audio file using Whisper."""
    svc = VoiceService()
    audio_data = await file.read()
    filename = file.filename or "audio.webm"
    result = await svc.transcribe_audio(audio_data, filename)
    return {"transcript": result}


@router.post("/diarize")
async def diarize_transcript(
    transcript: str,
    user: User = Depends(get_current_user),
) -> dict:
    """Detect speakers in a transcript."""
    svc = VoiceService()
    segments = await svc.detect_speakers(transcript)
    return {"segments": segments}
