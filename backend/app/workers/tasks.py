"""Celery tasks — real implementations for data collection, digests, and content generation.

All tasks use sync wrappers around async code since Celery workers are synchronous.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.competitor import Competitor
from app.models.content_plan import ContentPlan
from app.models.content_task import ContentTask
from app.models.report import Report
from app.models.subscription import Subscription, SubscriptionStatus
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


@celery_app.task(bind=True, max_retries=3)
def collect_competitor_data(self) -> dict:
    """Collect data from all active competitors across all platforms.

    Runs hourly via Celery Beat.
    Flow:
    1. Fetch all active competitors
    2. For each, run platform parsers
    3. Deduplicate via SimHash
    4. Embed new content → Qdrant
    5. Store in DB
    """
    logger.info("Starting competitor data collection")
    return _run_async(_collect_competitor_data_async())


async def _collect_competitor_data_async() -> dict:
    results = {"total_competitors": 0, "total_fetched": 0, "total_new": 0, "errors": []}

    async with async_session_factory() as db:
        # Get all active competitors
        stmt = select(Competitor).where(Competitor.is_active.is_(True))
        competitors = (await db.execute(stmt)).scalars().all()
        results["total_competitors"] = len(competitors)

        if not competitors:
            logger.info("No active competitors to collect data for")
            return results

        pipeline = IngestionPipeline(db)

        # Ensure Qdrant collection exists
        await pipeline.qdrant.ensure_collection()

        # Collect last 24h by default (overlap is handled by deduplication)
        since = datetime.now(timezone.utc) - timedelta(hours=24)

        for competitor in competitors:
            try:
                stats = await pipeline.process_competitor(competitor, since=since)
                results["total_fetched"] += stats["fetched"]
                results["total_new"] += stats["new"]
                if stats["errors"]:
                    results["errors"].extend(stats["errors"])
            except Exception as e:
                msg = f"Competitor {competitor.name}: {e}"
                logger.exception(msg)
                results["errors"].append(msg)

        await db.commit()

    logger.info(
        "Data collection complete: %d competitors, %d fetched, %d new posts",
        results["total_competitors"], results["total_fetched"], results["total_new"],
    )
    return results


# ── Weekly Digests ───────────────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3)
def generate_weekly_digests(self) -> dict:
    """Generate weekly digest reports for all users with active subscriptions.

    Runs weekly (Monday 9:00 UTC) via Celery Beat.
    """
    logger.info("Starting weekly digest generation")
    return _run_async(_generate_weekly_digests_async())


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


@celery_app.task(bind=True, max_retries=3)
def check_daily_alerts(self) -> dict:
    """Check for alert-worthy events across all users.

    Runs daily via Celery Beat.
    """
    logger.info("Starting daily alert check")
    return _run_async(_check_daily_alerts_async())


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


# ── Content Plan Generation ──────────────────────────────────────────────────


@celery_app.task(bind=True, max_retries=3)
def generate_content_plan(self, user_id: str, period: str = "weekly") -> dict:
    """Generate an AI-powered content plan for a user.

    Triggered on-demand via API.
    """
    logger.info("Generating %s content plan for user %s", period, user_id)
    return _run_async(_generate_content_plan_async(user_id, period))


async def _generate_content_plan_async(user_id: str, period: str) -> dict:
    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if not user:
            return {"status": "error", "message": f"User {user_id} not found"}

        generator = ReportGenerator(db)
        plan_data = await generator.generate_content_plan(user, period=period)

        # Create ContentPlan record
        plan = ContentPlan(
            user_id=user.id,
            period=period,
            status="draft",
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
                status="pending",
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


@celery_app.task(bind=True, max_retries=3)
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
            ContentTask.status == "approved",
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
                    task.status = "published"
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


@celery_app.task(bind=True, max_retries=3)
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


@celery_app.task(bind=True, max_retries=3)
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
