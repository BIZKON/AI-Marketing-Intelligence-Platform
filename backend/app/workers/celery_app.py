from celery import Celery

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
)

celery_app.conf.beat_schedule = {
    "collect-competitor-data": {
        "task": "app.workers.tasks.collect_competitor_data",
        "schedule": 3600.0,  # Every hour
    },
    "generate-weekly-digests": {
        "task": "app.workers.tasks.generate_weekly_digests",
        "schedule": {
            "type": "crontab",
            "hour": 9,
            "minute": 0,
            "day_of_week": 1,  # Monday
        },
    },
}

celery_app.autodiscover_tasks(["app.workers"])
