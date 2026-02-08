"""Telegram Export orchestrator — the main service coordinating the full export pipeline.

Connects to Telegram via encrypted session, fetches messages, processes media,
transcribes audio, persists metadata, and sends content into the RAG pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from app.models.export import (
    ExportJob,
    ExportJobStatus,
    ExportSource,
    ExportSourceType,
    MessageMeta,
    TelegramSession,
)
from app.services.export.analytics import ExportAnalytics
from app.services.export.fetcher import MessageFetcher
from app.services.export.media import MediaProcessor
from app.services.export.transcriber import WhisperTranscriber

logger = logging.getLogger(__name__)

# How often to flush progress to the database
_PROGRESS_FLUSH_INTERVAL = 50

# Source type mapping from entity info
_ENTITY_TYPE_MAP: dict[str, ExportSourceType] = {
    "channel": ExportSourceType.CHANNEL,
    "group": ExportSourceType.GROUP,
    "chat": ExportSourceType.CHAT,
}


class TelegramExportService:
    """Main orchestrator for Telegram data export into the RAG pipeline.

    Coordinates message fetching, media processing, transcription, metadata
    persistence, and RAG ingestion in a single export flow.
    """

    def __init__(
        self,
        db: AsyncSession,
        rag_pipeline: Any,
        media_processor: MediaProcessor,
        transcriber: WhisperTranscriber,
        analytics: ExportAnalytics,
    ) -> None:
        self._db = db
        self._rag = rag_pipeline
        self._media = media_processor
        self._transcriber = transcriber
        self._analytics = analytics

    # ── Connection ────────────────────────────────────────────────────────

    async def connect(self, session: TelegramSession) -> TelegramClient:
        """Decrypt session credentials and establish a Telethon connection.

        Parameters
        ----------
        session:
            A ``TelegramSession`` DB record with encrypted session string.

        Returns
        -------
        TelegramClient
            A connected and authorized Telethon client.

        Raises
        ------
        ValueError
            If the ``TELEGRAM_ENCRYPTION_KEY`` env var is missing.
        RuntimeError
            If the decrypted session fails to connect.
        """
        encryption_key = os.environ.get("TELEGRAM_ENCRYPTION_KEY")
        if not encryption_key:
            raise ValueError(
                "TELEGRAM_ENCRYPTION_KEY environment variable is required "
                "for decrypting Telegram sessions"
            )

        fernet = Fernet(encryption_key.encode())

        # Decrypt the session string
        session_string_encrypted = session.session_string_encrypted
        if not session_string_encrypted:
            raise ValueError(
                f"TelegramSession {session.id} has no encrypted session string"
            )

        session_string = fernet.decrypt(
            session_string_encrypted.encode(),
        ).decode()

        # Decrypt API hash
        api_hash = fernet.decrypt(
            session.api_hash_encrypted.encode(),
        ).decode()

        client = TelegramClient(
            StringSession(session_string),
            session.api_id,
            api_hash,
        )

        await client.connect()

        if not await client.is_user_authorized():
            await client.disconnect()
            raise RuntimeError(
                f"TelegramSession {session.id} is no longer authorized. "
                "User needs to re-authenticate."
            )

        logger.info(
            "Connected to Telegram via session %s (phone %s***)",
            session.id,
            session.phone[:4] if session.phone else "?",
        )

        # Update last_used_at
        session.last_used_at = datetime.now(timezone.utc)
        await self._db.flush()

        return client

    # ── Export entity ─────────────────────────────────────────────────────

    async def export_entity(
        self,
        user_id: uuid.UUID,
        session: TelegramSession,
        entity_id: int | str,
        config: dict[str, Any],
    ) -> ExportJob:
        """Execute a full export for a single Telegram entity.

        Orchestrates the complete pipeline:
        1. Connect to Telegram
        2. Retrieve entity information
        3. Create ExportJob and ExportSource records
        4. Iterate over messages, saving metadata and ingesting into RAG
        5. Process media and transcribe audio when enabled
        6. Update final statistics

        Parameters
        ----------
        user_id:
            The platform user requesting the export.
        session:
            The ``TelegramSession`` to connect with.
        entity_id:
            Telegram entity ID or username.
        config:
            Export configuration dict with optional keys:
            ``limit``, ``offset_id``, ``date_from``, ``date_to``,
            ``min_reactions``, ``transcribe_audio``, ``download_media``,
            ``language``.

        Returns
        -------
        ExportJob
            The completed (or failed) export job record.
        """
        client: TelegramClient | None = None
        job: ExportJob | None = None

        try:
            # 1. Connect to Telegram
            client = await self.connect(session)

            # 2. Get entity info
            fetcher = MessageFetcher(client)
            entity_info = await fetcher.get_entity_info(entity_id)

            # 3. Find or create ExportSource
            source = await self._get_or_create_source(
                user_id=user_id,
                entity_info=entity_info,
            )

            # 4. Create ExportJob
            job = ExportJob(
                user_id=user_id,
                session_id=session.id,
                source_id=source.id,
                source_type=_ENTITY_TYPE_MAP.get(
                    entity_info["type"],
                    ExportSourceType.CHANNEL,
                ),
                source_tg_id=str(entity_info["id"]),
                source_name=entity_info["title"] or str(entity_id),
                config=config,
                status=ExportJobStatus.PROCESSING,
                started_at=datetime.now(timezone.utc),
            )
            self._db.add(job)
            await self._db.flush()

            logger.info(
                "Started export job %s for entity %s (%s)",
                job.id,
                entity_id,
                entity_info["title"],
            )

            # 5. Iterate and process messages
            processed = 0
            total_chunks = 0
            authors_seen: set[int | None] = set()

            limit = config.get("limit", 500)
            offset_id = config.get("offset_id", 0)

            # Use source's last_message_id for incremental export
            if offset_id == 0 and source.last_message_id:
                offset_id = source.last_message_id

            date_from = config.get("date_from")
            date_to = config.get("date_to")
            if isinstance(date_from, str):
                date_from = datetime.fromisoformat(date_from)
            if isinstance(date_to, str):
                date_to = datetime.fromisoformat(date_to)

            min_reactions = config.get("min_reactions", 0)
            transcribe_enabled = config.get("transcribe_audio", False)
            download_enabled = config.get("download_media", False)
            language = config.get("language", "ru")

            max_message_id = 0

            async for msg_data in fetcher.fetch_messages(
                entity_id=entity_id,
                limit=limit,
                offset_id=offset_id,
                date_from=date_from,
                date_to=date_to,
                min_reactions=min_reactions,
            ):
                try:
                    await self._process_single_message(
                        msg_data=msg_data,
                        job=job,
                        source=source,
                        client=client,
                        transcribe_enabled=transcribe_enabled,
                        download_enabled=download_enabled,
                        language=language,
                    )

                    processed += 1
                    authors_seen.add(msg_data.get("author_id"))
                    msg_id = msg_data["message_id"]
                    if msg_id > max_message_id:
                        max_message_id = msg_id

                    # Flush progress periodically
                    if processed % _PROGRESS_FLUSH_INTERVAL == 0:
                        job.processed_messages = processed
                        await self._db.flush()
                        logger.info(
                            "Export %s progress: %d messages processed",
                            job.id,
                            processed,
                        )

                except FloodWaitError as e:
                    wait_seconds = e.seconds
                    logger.warning(
                        "FloodWaitError: sleeping %d seconds",
                        wait_seconds,
                    )
                    await asyncio.sleep(wait_seconds)
                    # Retry this message after waiting
                    try:
                        await self._process_single_message(
                            msg_data=msg_data,
                            job=job,
                            source=source,
                            client=client,
                            transcribe_enabled=transcribe_enabled,
                            download_enabled=download_enabled,
                            language=language,
                        )
                        processed += 1
                        authors_seen.add(msg_data.get("author_id"))
                    except Exception:
                        logger.exception(
                            "Failed to process message %d after flood wait",
                            msg_data["message_id"],
                        )

                except Exception:
                    logger.exception(
                        "Error processing message %d in export %s",
                        msg_data["message_id"],
                        job.id,
                    )

            # 6. Finalize job and source
            job.status = ExportJobStatus.COMPLETED
            job.processed_messages = processed
            job.total_messages = processed
            job.completed_at = datetime.now(timezone.utc)

            source.total_messages = (source.total_messages or 0) + processed
            source.total_authors = len(authors_seen - {None})
            source.last_export_at = datetime.now(timezone.utc)
            if max_message_id > 0:
                source.last_message_id = max_message_id

            await self._db.flush()

            logger.info(
                "Export job %s completed: %d messages, %d authors",
                job.id,
                processed,
                len(authors_seen - {None}),
            )

        except FloodWaitError as e:
            logger.error(
                "FloodWaitError during export setup: wait %d seconds",
                e.seconds,
            )
            if job:
                job.status = ExportJobStatus.FAILED
                job.error_message = (
                    f"Telegram rate limit: wait {e.seconds}s and retry"
                )
                await self._db.flush()

        except Exception as exc:
            logger.exception("Export job failed")
            if job:
                job.status = ExportJobStatus.FAILED
                job.error_message = str(exc)[:2000]
                job.completed_at = datetime.now(timezone.utc)
                await self._db.flush()

        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    logger.debug("Error disconnecting Telegram client", exc_info=True)

        if job is None:
            # Connection or setup failed before job was created
            job = ExportJob(
                user_id=user_id,
                session_id=session.id,
                source_type=ExportSourceType.CHANNEL,
                source_tg_id=str(entity_id),
                source_name=str(entity_id),
                config=config,
                status=ExportJobStatus.FAILED,
                error_message="Failed to initialize export",
                started_at=datetime.now(timezone.utc),
                completed_at=datetime.now(timezone.utc),
            )
            self._db.add(job)
            await self._db.flush()

        return job

    # ── Export folder ─────────────────────────────────────────────────────

    async def export_folder(
        self,
        user_id: uuid.UUID,
        session: TelegramSession,
        folder_id: int,
        config: dict[str, Any],
    ) -> list[ExportJob]:
        """Export all entities in a Telegram folder.

        Parameters
        ----------
        user_id:
            The platform user requesting the export.
        session:
            The ``TelegramSession`` to connect with.
        folder_id:
            Telegram folder (dialog filter) ID.
        config:
            Export configuration passed to each entity export.

        Returns
        -------
        list[ExportJob]
            One ExportJob per entity in the folder.
        """
        client: TelegramClient | None = None
        jobs: list[ExportJob] = []

        try:
            client = await self.connect(session)
            fetcher = MessageFetcher(client)
            dialogs = await fetcher.get_folder_dialogs(folder_id)

            logger.info(
                "Exporting folder %d: %d entities found",
                folder_id,
                len(dialogs),
            )

            # Disconnect before per-entity exports (each creates its own connection)
            await client.disconnect()
            client = None

            for dialog_info in dialogs:
                entity_id = dialog_info["id"]
                try:
                    job = await self.export_entity(
                        user_id=user_id,
                        session=session,
                        entity_id=entity_id,
                        config=config,
                    )
                    jobs.append(job)
                except Exception:
                    logger.exception(
                        "Failed to export entity %s from folder %d",
                        entity_id,
                        folder_id,
                    )

        except Exception:
            logger.exception("Failed to export folder %d", folder_id)

        finally:
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:
                    pass

        return jobs

    # ── Cancel ────────────────────────────────────────────────────────────

    async def cancel_export(self, job_id: uuid.UUID) -> None:
        """Mark an export job as cancelled.

        Parameters
        ----------
        job_id:
            The ``ExportJob.id`` to cancel.
        """
        stmt = select(ExportJob).where(ExportJob.id == job_id)
        result = await self._db.execute(stmt)
        job = result.scalar_one_or_none()

        if job is None:
            logger.warning("Cannot cancel: export job %s not found", job_id)
            return

        if job.status in (
            ExportJobStatus.COMPLETED,
            ExportJobStatus.FAILED,
            ExportJobStatus.CANCELLED,
        ):
            logger.info(
                "Export job %s already in terminal state: %s",
                job_id,
                job.status,
            )
            return

        job.status = ExportJobStatus.CANCELLED
        job.completed_at = datetime.now(timezone.utc)
        await self._db.flush()

        logger.info("Export job %s cancelled", job_id)

    # ── Private helpers ───────────────────────────────────────────────────

    async def _get_or_create_source(
        self,
        user_id: uuid.UUID,
        entity_info: dict[str, Any],
    ) -> ExportSource:
        """Find an existing ExportSource or create a new one."""
        telegram_id = entity_info["id"]

        stmt = select(ExportSource).where(
            ExportSource.user_id == user_id,
            ExportSource.telegram_id == telegram_id,
        )
        result = await self._db.execute(stmt)
        source = result.scalar_one_or_none()

        if source is not None:
            # Update title/username in case they changed
            source.title = entity_info["title"] or source.title
            source.username = entity_info.get("username") or source.username
            await self._db.flush()
            return source

        source = ExportSource(
            user_id=user_id,
            telegram_id=telegram_id,
            telegram_type=_ENTITY_TYPE_MAP.get(
                entity_info["type"],
                ExportSourceType.CHANNEL,
            ),
            username=entity_info.get("username"),
            title=entity_info["title"] or str(telegram_id),
        )
        self._db.add(source)
        await self._db.flush()

        logger.info(
            "Created ExportSource %s for entity %d (@%s)",
            source.id,
            telegram_id,
            entity_info.get("username"),
        )
        return source

    async def _process_single_message(
        self,
        msg_data: dict[str, Any],
        job: ExportJob,
        source: ExportSource,
        client: TelegramClient,
        transcribe_enabled: bool,
        download_enabled: bool,
        language: str,
    ) -> None:
        """Process a single message: save metadata, handle media, ingest to RAG."""
        raw_message = msg_data["raw_message"]
        text = msg_data["text"] or ""
        transcription_text = ""
        has_transcription = False
        media_s3_info: dict[str, Any] | None = None

        # Handle media
        if msg_data["has_media"] and (download_enabled or transcribe_enabled):
            media_type = msg_data["media_type"]

            if download_enabled:
                media_s3_info = await self._media.download_media(
                    client=client,
                    message=raw_message,
                    export_id=str(job.id),
                )

            # Transcribe voice/video_note messages
            if (
                transcribe_enabled
                and media_type in ("voice", "video_note")
                and media_s3_info
                and media_s3_info.get("s3_key")
            ):
                transcription = await self._transcriber.transcribe_from_s3(
                    s3_storage=self._media._s3,
                    s3_key=media_s3_info["s3_key"],
                    language=language,
                )
                transcription_text = transcription.get("text", "")
                if transcription_text:
                    has_transcription = True

        # Combine text and transcription for RAG ingestion
        combined_text = text
        if transcription_text:
            combined_text = (
                f"{text}\n\n[Transcription]\n{transcription_text}"
                if text
                else transcription_text
            )

        # Save MessageMeta to PostgreSQL
        meta = MessageMeta(
            source_id=source.id,
            export_job_id=job.id,
            telegram_message_id=msg_data["message_id"],
            author_telegram_id=msg_data.get("author_id"),
            author_username=msg_data.get("author_username"),
            author_name=msg_data.get("author_name"),
            date=msg_data["date"],
            reactions_count=msg_data.get("reactions_count", 0),
            views_count=msg_data.get("views", 0),
            forwards_count=msg_data.get("forwards", 0),
            has_media=msg_data["has_media"],
            media_type=msg_data.get("media_type"),
            has_transcription=has_transcription,
            text_length=len(combined_text),
        )
        self._db.add(meta)

        # Ingest into RAG pipeline if there is meaningful content
        if combined_text.strip() and self._rag is not None:
            try:
                await self._rag.ingest_message(
                    text=combined_text,
                    metadata={
                        "source_id": str(source.id),
                        "export_job_id": str(job.id),
                        "message_meta_id": str(meta.id),
                        "telegram_message_id": msg_data["message_id"],
                        "author_id": msg_data.get("author_id"),
                        "author_username": msg_data.get("author_username"),
                        "date": (
                            msg_data["date"].isoformat()
                            if msg_data["date"]
                            else None
                        ),
                        "reactions_count": msg_data.get("reactions_count", 0),
                        "views": msg_data.get("views", 0),
                        "has_media": msg_data["has_media"],
                        "media_type": msg_data.get("media_type"),
                    },
                )
            except Exception:
                logger.warning(
                    "RAG ingestion failed for message %d, metadata still saved",
                    msg_data["message_id"],
                    exc_info=True,
                )
