from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "marketing_platform",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    # Task timeouts
    task_soft_time_limit=300,  # 5 min soft limit
    task_time_limit=600,  # 10 min hard limit
    # Queue routing
    task_routes={
        "app.workers.tasks.collect_competitor_data": {"queue": "collection"},
        "app.workers.tasks.generate_voice_report": {"queue": "media"},
        "app.workers.tasks.generate_video_report": {"queue": "media"},
        "app.workers.tasks.run_export": {"queue": "export"},
        "app.workers.tasks.*": {"queue": "default"},
    },
    task_default_queue="default",
)

celery_app.conf.beat_schedule = {
    "collect-competitor-data": {
        "task": "app.workers.tasks.collect_competitor_data",
        "schedule": 3600.0,  # Every hour
    },
    "generate-weekly-digests": {
        "task": "app.workers.tasks.generate_weekly_digests",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),  # Monday 09:00 UTC
    },
    "check-daily-alerts": {
        "task": "app.workers.tasks.check_daily_alerts",
        "schedule": crontab(hour=10, minute=0),  # Daily at 10:00 UTC
    },
    "process-scheduled-publications": {
        "task": "app.workers.tasks.process_scheduled_publications",
        "schedule": 300.0,  # Every 5 minutes
    },
}

celery_app.autodiscover_tasks(["app.workers"])
