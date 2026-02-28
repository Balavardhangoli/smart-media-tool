"""
tasks/celery_app.py
Celery application configuration and task definitions.
Tasks run in background workers separate from the API server.
"""
from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

# ── Celery app ─────────────────────────────────────────────
celery_app = Celery(
    "smart_media_fetcher",
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
    worker_max_tasks_per_child=100,     # Restart worker after 100 tasks (memory safety)
    task_soft_time_limit=120,           # Soft limit: 2 min
    task_time_limit=180,                # Hard limit: 3 min
    beat_schedule={
        # Run temp file cleanup every 15 minutes
        "cleanup-temp-files": {
            "task": "app.tasks.maintenance.cleanup_temp_files_task",
            "schedule": crontab(minute="*/15"),
        },
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
