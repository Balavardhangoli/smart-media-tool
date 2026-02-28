"""
utils/file_utils.py
Safe filename handling, temp file management, MIME type detection.
"""
import os
import re
import uuid
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Characters not allowed in filenames (security: prevent path traversal)
UNSAFE_CHARS = re.compile(r'[^\w\s\-.]')
MAX_FILENAME_LENGTH = 200


def sanitize_filename(name: str, fallback: str = "download") -> str:
    """
    Sanitize a filename:
    - Strip path separators (prevents path traversal)
    - Remove special characters
    - Limit length
    - Never allow empty result
    """
    if not name:
        return fallback

    # Strip any directory component
    name = os.path.basename(name)

    # Remove null bytes and control characters
    name = name.replace("\x00", "").strip()

    # Replace spaces and unsafe characters
    name = UNSAFE_CHARS.sub("_", name)
    name = re.sub(r"_+", "_", name).strip("_")

    # Limit length (keep extension)
    if len(name) > MAX_FILENAME_LENGTH:
        ext = Path(name).suffix
        stem = name[: MAX_FILENAME_LENGTH - len(ext)]
        name = stem + ext

    return name or fallback


def generate_temp_path(extension: str = "") -> Path:
    """Generate a unique temp file path inside the configured temp directory."""
    temp_dir = Path(settings.temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    filename = str(uuid.uuid4()) + (extension if extension.startswith(".") else f".{extension}" if extension else "")
    return temp_dir / filename


def format_file_size(size_bytes: int) -> str:
    """Human-readable file size string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 ** 2:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 ** 3:
        return f"{size_bytes / 1024**2:.1f} MB"
    else:
        return f"{size_bytes / 1024**3:.2f} GB"


async def cleanup_temp_files() -> int:
    """
    Delete temp files older than AUTO_DELETE_TEMP_MINUTES.
    Should be run as a scheduled Celery task.
    Returns count of deleted files.
    """
    temp_dir = Path(settings.temp_dir)
    if not temp_dir.exists():
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=settings.auto_delete_temp_minutes)
    deleted = 0

    for file in temp_dir.iterdir():
        try:
            if file.is_file():
                mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
                if mtime < cutoff:
                    file.unlink()
                    deleted += 1
        except Exception as e:
            logger.warning("temp_cleanup_error", file=str(file), error=str(e))

    logger.info("temp_cleanup_done", deleted=deleted)
    return deleted


MIME_TYPE_MAP = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/gif":  ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "video/mp4":  ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "audio/mpeg": ".mp3",
    "audio/wav":  ".wav",
    "audio/ogg":  ".ogg",
    "audio/flac": ".flac",
    "application/pdf": ".pdf",
    "application/zip": ".zip",
}


def extension_from_mime(mime: str) -> str:
    return MIME_TYPE_MAP.get(mime.split(";")[0].strip(), "")
