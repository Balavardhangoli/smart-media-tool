"""
tasks/maintenance.py
Scheduled maintenance tasks run by Celery Beat.
"""
import asyncio
from app.tasks.celery_app import celery_app
from app.core.logging import get_logger

logger = get_logger(__name__)


@celery_app.task(name="app.tasks.maintenance.cleanup_temp_files_task", bind=True)
def cleanup_temp_files_task(self):
    """Delete expired temporary files from the temp directory."""
    from app.utils.file_utils import cleanup_temp_files
    try:
        deleted = asyncio.run(cleanup_temp_files())
        logger.info("cleanup_task_done", deleted=deleted)
        return {"deleted": deleted}
    except Exception as exc:
        logger.error("cleanup_task_error", error=str(exc))
        raise self.retry(exc=exc, countdown=60, max_retries=3)
