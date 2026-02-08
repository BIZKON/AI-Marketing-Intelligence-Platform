"""Celery tasks — real implementations for data collection, digests, and content generation.

All tasks use sync wrappers around async code since Celery workers are synchronous.
"""

import asyncio
import logging
import uuid as uuid_mod
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.competitor import Competitor
from app.models.content_plan import ContentPlan, PlanStatus
from app.models.content_task import ContentTask, TaskStatus
from app.models.export import ExportJob, ExportJobStatus, TelegramSession
from app.models.export import ExportJob, ExportJobStatus, ExportSource, TelegramSession
from app.models.report import Report
from app.models.subscription import PlanType, Subscription, SubscriptionStatus
from app.models.user import User
from app.services.report_generator import ReportGenerator
from app.services.vectordb.pipeline import IngestionPipeline
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine in a new event loop (for Celery workers)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Data Collection ──────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60, soft_time_limit=600, time_limit=660)
def collect_competitor_data(self) -> dict:
    """Fan-out data collection: dispatches one sub-task per competitor.

    Runs hourly via Celery Beat.
    """
    logger.info("Starting competitor data collection (fan-out)")
    try:
        return _run_async(_dispatch_competitor_collection())
    except Exception as exc:
        logger.exception("Competitor data collection dispatch failed, retrying")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30, soft_time_limit=300, time_limit=360)
def collect_single_competitor(self, competitor_id: str) -> dict:
    """Collect data for a single competitor. Dispatched by collect_competitor_data."""
    logger.info("Collecting data for competitor %s", competitor_id)
    try:
        return _run_async(_collect_single_competitor_async(competitor_id))
    except Exception as exc:
        logger.exception("Collection for competitor %s failed, retrying", competitor_id)
        raise self.retry(exc=exc)


async def _dispatch_competitor_collection() -> dict:
    """Discover active competitors and dispatch individual tasks."""
    async with async_session_factory() as db:
        stmt = (
            select(Competitor.id)
            .join(User, Competitor.user_id == User.id)
            .join(Subscription, Subscription.user_id == User.id)
            .where(
                Competitor.is_active.is_(True),
                User.is_active.is_(True),
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
            .distinct()
        )
        competitor_ids = (await db.execute(stmt)).scalars().all()

    dispatched = 0
    for cid in competitor_ids:
        collect_single_competitor.delay(str(cid))
        dispatched += 1

    logger.info("Dispatched %d competitor collection tasks", dispatched)
    return {"dispatched": dispatched}


async def _collect_single_competitor_async(competitor_id: str) -> dict:
    """Collect data for one competitor."""
    async with async_session_factory() as db:
        competitor = await db.get(Competitor, uuid_mod.UUID(competitor_id))
        if not competitor or not competitor.is_active:
            return {"status": "skipped", "reason": "inactive or not found"}

        pipeline = IngestionPipeline(db)
        await pipeline.qdrant.ensure_collection()
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        stats = await pipeline.process_competitor(competitor, since=since)
        await db.commit()

    return {
        "competitor_id": competitor_id,
        "fetched": stats["fetched"],
        "new": stats["new"],
        "errors": stats.get("errors", []),
    }


# ── Weekly Digests ───────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, soft_time_limit=900, time_limit=960)
def generate_weekly_digests(self) -> dict:
    """Generate weekly digest reports for all users with active subscriptions.

    Runs weekly (Monday 9:00 UTC) via Celery Beat.
    """
    logger.info("Starting weekly digest generation")
    try:
        return _run_async(_generate_weekly_digests_async())
    except Exception as exc:
        logger.exception("Weekly digest generation failed, retrying")
        raise self.retry(exc=exc)


async def _generate_weekly_digests_async() -> dict:
    results = {"total_users": 0, "digests_generated": 0, "errors": []}

    async with async_session_factory() as db:
        # Find users with active subscriptions
        stmt = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                User.is_active.is_(True),
            )
            .distinct()
        )
        users = (await db.execute(stmt)).scalars().all()
        results["total_users"] = len(users)

        generator = ReportGenerator(db)

        for user in users:
            try:
                report = await generator.generate_digest(user, days=7)
                results["digests_generated"] += 1
                logger.info("Generated digest %s for user %s", report.id, user.id)
            except Exception as e:
                msg = f"User {user.id}: {e}"
                logger.exception(msg)
                results["errors"].append(msg)

        await db.commit()

    logger.info(
        "Weekly digests: %d users, %d generated, %d errors",
        results["total_users"], results["digests_generated"], len(results["errors"]),
    )
    return results


# ── Daily Alerts ─────────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, soft_time_limit=600, time_limit=660)
def check_daily_alerts(self) -> dict:
    """Check for alert-worthy events across all users.

    Runs daily via Celery Beat.
    """
    logger.info("Starting daily alert check")
    try:
        return _run_async(_check_daily_alerts_async())
    except Exception as exc:
        logger.exception("Daily alert check failed, retrying")
        raise self.retry(exc=exc)


async def _check_daily_alerts_async() -> dict:
    results = {"total_users": 0, "alerts_generated": 0, "errors": []}

    async with async_session_factory() as db:
        stmt = (
            select(User)
            .join(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                User.is_active.is_(True),
            )
            .distinct()
        )
        users = (await db.execute(stmt)).scalars().all()
        results["total_users"] = len(users)

        generator = ReportGenerator(db)

        for user in users:
            try:
                alerts = await generator.check_alerts(user, hours=24)
                results["alerts_generated"] += len(alerts)
            except Exception as e:
                msg = f"User {user.id}: {e}"
                logger.exception(msg)
                results["errors"].append(msg)

        await db.commit()

    logger.info(
        "Daily alerts: %d users checked, %d alerts generated",
        results["total_users"], results["alerts_generated"],
    )
    return results


# ── Single Draft Generation (#043) ──────────────────────────────────────────


@celery_app.task(bind=True, max_retries=2, soft_time_limit=120, time_limit=150)
def generate_single_draft(self, task_id: str, user_id: str) -> dict:
    """Generate an AI draft for a single content task. Dispatched from HTTP handler."""
    logger.info("Generating draft for task %s user %s", task_id, user_id)
    return _run_async(_generate_single_draft_async(task_id, user_id))


async def _generate_single_draft_async(task_id: str, user_id: str) -> dict:
    async with async_session_factory() as db:
        task = await db.get(ContentTask, uuid_mod.UUID(task_id))
        user = await db.get(User, uuid_mod.UUID(user_id))
        if not task or not user:
            return {"status": "error", "message": "Task or user not found"}

        from app.services.content_generator import ContentGenerator
        generator = ContentGenerator(db)
        updated_task = await generator.generate_draft(task, user)
        await db.commit()

        return {
            "status": "ok",
            "task_id": task_id,
            "task_status": updated_task.status.value,
        }


# ── Content Plan Generation ──────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def generate_content_plan(self, user_id: str, period: str = "weekly") -> dict:
    """Generate an AI-powered content plan for a user.

    Triggered on-demand via API.
    """
    logger.info("Generating %s content plan for user %s", period, user_id)
    return _run_async(_generate_content_plan_async(user_id, period))


async def _generate_content_plan_async(user_id: str, period: str) -> dict:
    async with async_session_factory() as db:
        user = await db.get(User, uuid_mod.UUID(user_id))
        if not user:
            return {"status": "error", "message": f"User {user_id} not found"}

        # Verify user has an active subscription with Creator+ plan
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING]),
            )
        )
        sub = sub_result.scalar_one_or_none()
        if not sub or sub.plan not in (PlanType.CREATOR, PlanType.AUTOPILOT, PlanType.ENTERPRISE):
            return {"status": "error", "message": "Active Creator+ subscription required"}

        generator = ReportGenerator(db)
        plan_data = await generator.generate_content_plan(user, period=period)

        # Create ContentPlan record
        plan = ContentPlan(
            user_id=user.id,
            period=period,
            status=PlanStatus.DRAFT,
            content=plan_data.get("structured_data", {}),
            ai_response=plan_data.get("content", ""),
        )
        db.add(plan)
        await db.flush()

        # Create ContentTask records from structured plan
        tasks_data = plan_data.get("structured_data", {}).get("tasks", [])
        for task_data in tasks_data:
            task = ContentTask(
                user_id=user.id,
                content_plan_id=plan.id,
                title=task_data.get("title", "Untitled"),
                platform=task_data.get("platform", ""),
                content_type=task_data.get("format", "text"),
                body=task_data.get("topic", ""),
                status=TaskStatus.PENDING,
                metadata_json={
                    "key_points": task_data.get("key_points", []),
                    "hashtags": task_data.get("hashtags", []),
                    "suggested_day": task_data.get("suggested_day", ""),
                },
            )
            db.add(task)

        await db.commit()

        return {
            "status": "ok",
            "plan_id": str(plan.id),
            "tasks_created": len(tasks_data),
        }


# ── Auto-Publishing ──────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def process_scheduled_publications(self) -> dict:
    """Publish all approved tasks that have passed their scheduled_at time.

    Runs every 5 minutes via Celery Beat.
    """
    logger.info("Processing scheduled publications")
    return _run_async(_process_scheduled_publications_async())


async def _process_scheduled_publications_async() -> dict:
    results = {"published": 0, "failed": 0, "errors": []}

    async with async_session_factory() as db:
        now = datetime.now(timezone.utc)

        # Find tasks that are approved, scheduled, and past their scheduled time
        stmt = select(ContentTask).where(
            ContentTask.status == TaskStatus.APPROVED,
            ContentTask.scheduled_at.isnot(None),
            ContentTask.scheduled_at <= now,
        )
        tasks = (await db.execute(stmt)).scalars().all()

        if not tasks:
            return results

        from app.services.publisher import PublisherService
        publisher = PublisherService()

        for task in tasks:
            try:
                pub_result = await publisher.publish(task)

                if pub_result.get("status") == "ok":
                    task.status = TaskStatus.PUBLISHED
                    task.published_at = now
                    task.metadata_json = {
                        **(task.metadata_json or {}),
                        "published_url": pub_result.get("url"),
                        "auto_published": True,
                    }
                    results["published"] += 1
                    logger.info("Auto-published task %s to %s", task.id, task.platform)
                else:
                    results["failed"] += 1
                    results["errors"].append(
                        f"Task {task.id}: {pub_result.get('message', 'Unknown error')}"
                    )
            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"Task {task.id}: {e}")
                logger.exception("Failed to auto-publish task %s", task.id)

        await db.commit()

    logger.info(
        "Scheduled publications: %d published, %d failed",
        results["published"], results["failed"],
    )
    return results


# ── Voice Report ──────────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def generate_voice_report(self, voice_report_id: str, source_report_id: str) -> dict:
    """Convert a report to voice using ElevenLabs TTS.

    Flow: build speech script → ElevenLabs API → upload .ogg to S3 → update report.
    """
    logger.info("Generating voice report %s from source %s", voice_report_id, source_report_id)
    return _run_async(_generate_voice_report_async(voice_report_id, source_report_id))


async def _generate_voice_report_async(voice_report_id: str, source_report_id: str) -> dict:
    from app.services.media.voice_generator import VoiceGenerator

    async with async_session_factory() as db:
        voice_report = await db.get(Report, voice_report_id)
        if not voice_report:
            return {"status": "error", "message": f"Voice report {voice_report_id} not found"}

        source_report = await db.get(Report, source_report_id)
        if not source_report:
            voice_report.content = {**(voice_report.content or {}), "status": "error", "error": "Source report not found"}
            await db.commit()
            return {"status": "error", "message": f"Source report {source_report_id} not found"}

        try:
            generator = VoiceGenerator()
            result = await generator.generate_voice_report(
                report_content=source_report.content or {},
                report_markdown=source_report.content_markdown,
                title=source_report.title or "",
            )

            voice_report.media_url = result["url"]
            voice_report.content = {
                **(voice_report.content or {}),
                "status": "completed",
                "s3_key": result["s3_key"],
                "duration_estimate": result["duration_estimate"],
                "script_length": result["script_length"],
            }
            await db.commit()

            logger.info("Voice report %s completed: %s", voice_report_id, result["s3_key"])
            return {"status": "ok", "report_id": voice_report_id, **result}

        except Exception as e:
            voice_report.content = {**(voice_report.content or {}), "status": "error", "error": str(e)}
            await db.commit()
            logger.exception("Voice report %s failed", voice_report_id)
            return {"status": "error", "report_id": voice_report_id, "message": str(e)}


# ── Video Report ──────────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3, soft_time_limit=600, time_limit=660)
def generate_video_report(self, video_report_id: str, source_report_id: str) -> dict:
    """Generate a video report with HeyGen avatar and chart overlays.

    Flow: render charts → HeyGen API → poll → download → S3 → update report.
    """
    logger.info("Generating video report %s from source %s", video_report_id, source_report_id)
    return _run_async(_generate_video_report_async(video_report_id, source_report_id))


async def _generate_video_report_async(video_report_id: str, source_report_id: str) -> dict:
    from app.services.media.video_generator import VideoGenerator

    async with async_session_factory() as db:
        video_report = await db.get(Report, video_report_id)
        if not video_report:
            return {"status": "error", "message": f"Video report {video_report_id} not found"}

        source_report = await db.get(Report, source_report_id)
        if not source_report:
            video_report.content = {**(video_report.content or {}), "status": "error", "error": "Source report not found"}
            await db.commit()
            return {"status": "error", "message": f"Source report {source_report_id} not found"}

        try:
            generator = VideoGenerator()
            result = await generator.generate_video_report(
                report_content=source_report.content or {},
                report_markdown=source_report.content_markdown,
                title=source_report.title or "",
            )

            video_report.media_url = result["url"]
            video_report.content = {
                **(video_report.content or {}),
                "status": "completed",
                "s3_key": result["s3_key"],
                "heygen_video_id": result.get("heygen_video_id"),
                "video_size": result.get("video_size"),
            }
            await db.commit()

            logger.info("Video report %s completed: %s", video_report_id, result["s3_key"])
            return {"status": "ok", "report_id": video_report_id, **result}

        except Exception as e:
            video_report.content = {**(video_report.content or {}), "status": "error", "error": str(e)}
            await db.commit()
            logger.exception("Video report %s failed", video_report_id)
            return {"status": "error", "report_id": video_report_id, "message": str(e)}


# ── Telegram Export ──────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120, soft_time_limit=1800, time_limit=1860)
def run_export(self, job_id: str) -> dict:
    """Execute a Telegram data export job.

    Fetches messages via Telethon, processes media, transcribes audio,
    persists metadata, and ingests content into the RAG pipeline.

    Dispatched from the POST /tg-export/jobs endpoint.
    """
    logger.info("Starting Telegram export job %s", job_id)
@celery_app.task(bind=True, max_retries=2, soft_time_limit=1800, time_limit=1860)
def run_export(self, job_id: str) -> dict:
    """Execute a Telegram export job.

    Dispatched from the /telegram-export/jobs endpoint.
    Runs on the 'export' queue with extended time limits for large channels.
    """
    logger.info("Starting export job %s", job_id)
    try:
        return _run_async(_run_export_async(job_id))
    except Exception as exc:
        logger.exception("Export job %s failed, retrying", job_id)
        # Mark job as failed before retrying
        _run_async(_mark_export_failed(job_id, str(exc)))
        raise self.retry(exc=exc)


async def _run_export_async(job_id: str) -> dict:
    """Async implementation of the export task."""
        raise self.retry(exc=exc, countdown=60)


async def _run_export_async(job_id: str) -> dict:
    from app.services.export.analytics import ExportAnalytics
    from app.services.export.media import MediaProcessor
    from app.services.export.telegram_export import TelegramExportService
    from app.services.export.transcriber import WhisperTranscriber
    from app.services.vectordb.pipeline import IngestionPipeline

    async with async_session_factory() as db:
        job = await db.get(ExportJob, uuid_mod.UUID(job_id))
        if not job:
            return {"status": "error", "message": f"Export job {job_id} not found"}

        if job.status == ExportJobStatus.CANCELLED:
            return {"status": "cancelled", "job_id": job_id}

        # Get the Telegram session
        tg_session = await db.get(TelegramSession, job.session_id)
        if not tg_session or not tg_session.is_active:
            job.status = ExportJobStatus.FAILED
            job.error_message = "Telegram session not found or inactive"
            await db.commit()
            return {"status": "error", "message": "Session not available"}

        # Initialize service dependencies
        from app.services.export.analytics import ExportAnalytics
        from app.services.export.media import MediaProcessor
        from app.services.export.telegram_export import TelegramExportService
        from app.services.export.transcriber import WhisperTranscriber
        from app.services.rag.ingestion import RAGIngestionPipeline

        rag_pipeline = RAGIngestionPipeline(db)
        await rag_pipeline.ensure_collection()
        if job.status not in (ExportJobStatus.PENDING, ExportJobStatus.PROCESSING):
            return {"status": "skipped", "message": f"Job {job_id} has status {job.status.value}"}

        # Load the Telegram session
        tg_session = await db.get(TelegramSession, job.session_id)
        if not tg_session or not tg_session.is_active:
            job.status = ExportJobStatus.FAILED
            job.error_message = "Telegram session is inactive or not found"
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()
            return {"status": "error", "message": "No active Telegram session"}

        # Load source
        source = await db.get(ExportSource, job.source_id) if job.source_id else None

        # Initialize service dependencies
        rag_pipeline = IngestionPipeline(db)
        await rag_pipeline.qdrant.ensure_collection()

        media_processor = MediaProcessor()
        transcriber = WhisperTranscriber()
        analytics = ExportAnalytics(db)

        export_service = TelegramExportService(
        service = TelegramExportService(
            db=db,
            rag_pipeline=rag_pipeline,
            media_processor=media_processor,
            transcriber=transcriber,
            analytics=analytics,
        )

        # Determine entity to export
        entity_id: int | str = job.source_tg_id
        if entity_id.lstrip("-").isdigit():
            entity_id = int(entity_id)

        # Run the export
        completed_job = await export_service.export_entity(
        # Determine entity_id from source or job
        entity_id: int | str = job.source_tg_id
        if source and source.username:
            entity_id = source.username
        elif source:
            entity_id = source.telegram_id

        # Run the export
        completed_job = await service.export_entity(
            user_id=job.user_id,
            session=tg_session,
            entity_id=entity_id,
            config=job.config or {},
        )

        await db.commit()

        logger.info(
            "Export job %s finished with status %s: %d messages",
            job_id,
            completed_job.status.value,
            completed_job.processed_messages or 0,
        )

        return {
            "status": completed_job.status.value,
            "job_id": job_id,
            "processed_messages": completed_job.processed_messages or 0,
            "total_chunks": completed_job.total_chunks or 0,
        }


async def _mark_export_failed(job_id: str, error: str) -> None:
    """Mark an export job as failed in the database."""
    try:
        async with async_session_factory() as db:
            job = await db.get(ExportJob, uuid_mod.UUID(job_id))
            if job and job.status not in (
                ExportJobStatus.COMPLETED,
                ExportJobStatus.CANCELLED,
            ):
                job.status = ExportJobStatus.FAILED
                job.error_message = error[:2000]
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()
    except Exception:
        logger.exception("Failed to mark export job %s as failed", job_id)
        return {
            "status": completed_job.status.value,
            "job_id": str(completed_job.id),
            "processed_messages": completed_job.processed_messages,
        }


@celery_app.task(bind=True, max_retries=3, soft_time_limit=300, time_limit=360)
def auto_export_sources(self) -> dict:
    """Re-export all sources with auto_export=True.

    Runs on a schedule via Celery Beat. For each source with auto_export enabled,
    dispatches a separate run_export task to the export queue.
    """
    logger.info("Starting auto-export check for sources with auto_export=True")
    try:
        return _run_async(_auto_export_sources_async())
    except Exception as exc:
        logger.exception("Auto-export sources check failed, retrying")
        raise self.retry(exc=exc)


async def _auto_export_sources_async() -> dict:
    results = {"dispatched": 0, "skipped": 0, "errors": []}

    async with async_session_factory() as db:
        # Find sources with auto_export enabled that have an active session
        stmt = (
            select(ExportSource)
            .where(ExportSource.auto_export.is_(True))
        )
        sources = (await db.execute(stmt)).scalars().all()

        for source in sources:
            try:
                # Check for active session
                session_stmt = select(TelegramSession).where(
                    TelegramSession.user_id == source.user_id,
                    TelegramSession.is_active.is_(True),
                ).order_by(TelegramSession.created_at.desc()).limit(1)
                session_result = await db.execute(session_stmt)
                tg_session = session_result.scalar_one_or_none()

                if not tg_session:
                    results["skipped"] += 1
                    continue

                # Check there's no running export for this source
                running_stmt = select(ExportJob).where(
                    ExportJob.source_id == source.id,
                    ExportJob.status.in_([
                        ExportJobStatus.PENDING,
                        ExportJobStatus.PROCESSING,
                        ExportJobStatus.CHUNKING,
                        ExportJobStatus.EMBEDDING,
                    ]),
                )
                running_result = await db.execute(running_stmt)
                if running_result.scalar_one_or_none():
                    results["skipped"] += 1
                    continue

                # Create a new export job
                job = ExportJob(
                    user_id=source.user_id,
                    session_id=tg_session.id,
                    source_id=source.id,
                    source_type=source.telegram_type,
                    source_tg_id=source.username or str(source.telegram_id),
                    source_name=source.title,
                    config={"auto": True},
                    status=ExportJobStatus.PENDING,
                )
                db.add(job)
                await db.flush()

                # Dispatch to export queue
                run_export.delay(str(job.id))
                results["dispatched"] += 1

                logger.info(
                    "Auto-export dispatched for source %s (%s)",
                    source.id,
                    source.title,
                )

            except Exception as e:
                msg = f"Source {source.id}: {e}"
                logger.exception(msg)
                results["errors"].append(msg)

        await db.commit()

    logger.info(
        "Auto-export: %d dispatched, %d skipped, %d errors",
        results["dispatched"],
        results["skipped"],
        len(results["errors"]),
    )
    return results
