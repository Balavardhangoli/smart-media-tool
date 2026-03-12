"""
api/routes/download.py
Download API endpoints:
  POST /analyze  — detect platform, return media options
  POST /fetch    — stream a file to the client
  POST /bulk     — analyze multiple URLs
"""
import asyncio
import mimetypes
import urllib.parse
from typing import Optional, AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import DownloadHistory, AuditLog
from app.schemas.download import (
    AnalyzeRequest, AnalyzeResponse, BulkAnalyzeRequest,
    BulkAnalyzeResponse, FetchRequest, MediaOptionSchema,
)
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.detector import detect_platform
from app.services.downloader import process_url, DownloadResult
from app.utils.ssrf_guard import validate_url, SSRFError
from app.utils.file_utils import sanitize_filename, format_file_size

logger = get_logger(__name__)
router = APIRouter(prefix="/download", tags=["download"])

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}


def _client_ip(request: Request) -> str:
    xff = request.headers.get("X-Forwarded-For")
    return xff.split(",")[0].strip() if xff else request.client.host


async def _log_download(db: AsyncSession, url: str, platform: str,
                         media_type: str, ip: str, status: str,
                         user_id=None, error: Optional[str] = None) -> None:
    entry = DownloadHistory(
        user_id=user_id, source_url=url, media_type=media_type,
        platform=platform, status=status, error_msg=error, ip_address=ip,
    )
    db.add(entry)
    await db.commit()


# ──────────────────────────────────────────────────────────
#  ANALYZE ENDPOINT
# ──────────────────────────────────────────────────────────
@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_url(
    body:    AnalyzeRequest,
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """
    Analyze a URL and return available media options.
    Results are cached in Redis for CACHE_TTL_SECONDS.
    """
    url     = body.url
    quality = body.quality or "best"
    ip      = _client_ip(request)

    # ── Cache check ────────────────────────────────────────
    cache_key = make_cache_key("analyze", f"{url}:{quality}")
    cached    = await cache_get(cache_key)
    if cached:
        logger.info("cache_hit_analyze", url=url, ip=ip)
        return AnalyzeResponse(**cached)

    # ── Detect & process ───────────────────────────────────
    logger.info("analyze_start", url=url, ip=ip)
    detection = detect_platform(url)
    result: DownloadResult = await process_url(detection, quality=quality)

    response = AnalyzeResponse(
        success=result.success,
        url=url,
        platform=result.platform,
        media_type=detection.media_type.value,
        title=result.title,
        thumbnail=result.thumbnail,
        description=result.description,
        options=[
            MediaOptionSchema(
                label=o.label, url=o.url, media_type=o.media_type,
                mime_type=o.mime_type, file_size=o.file_size,
                width=o.width, height=o.height, format=o.format,
                thumbnail=o.thumbnail,
            )
            for o in result.options
        ],
        error=result.error,
    )

    # ── Cache result ───────────────────────────────────────
    if result.success:
        await cache_set(cache_key, response.model_dump())

    # ── Log to DB (non-blocking) ───────────────────────────
  try:
    entry = DownloadHistory(
        source_url=url,
        media_type=detection.media_type.value,
        platform=result.platform or "unknown",
        status="completed" if result.success else "failed",
        error_msg=result.error,
        ip_address=ip,
    )
    db.add(entry)
    await db.commit()
except Exception:
    pass

    return response


# ──────────────────────────────────────────────────────────
#  STREAM/FETCH ENDPOINT
# ──────────────────────────────────────────────────────────
@router.post("/fetch")
async def fetch_and_stream(
    body:    FetchRequest,
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """
    Stream a media file directly to the client.
    Validates URL, applies size limit, streams with proper headers.
    """
    try:
        url = validate_url(body.url)
    except SSRFError as e:
        raise HTTPException(status_code=400, detail=str(e))

    filename = sanitize_filename(body.filename or url.split("/")[-1] or "download")

    async def stream_generator() -> AsyncIterator[bytes]:
        total = 0
        async with httpx.AsyncClient(
            headers=BROWSER_HEADERS,
            timeout=httpx.Timeout(settings.http_timeout_seconds),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    total += len(chunk)
                    if total > settings.max_file_size_bytes:
                        raise HTTPException(413, detail="File exceeds size limit.")
                    yield chunk

    # Get content-type for response headers
    media_type = "application/octet-stream"
    try:
        async with httpx.AsyncClient(headers=BROWSER_HEADERS, timeout=10) as client:
            head = await client.head(url, follow_redirects=True)
            ct   = head.headers.get("content-type", "")
            if ct and "/" in ct:
                media_type = ct.split(";")[0].strip()
    except Exception:
        pass

    return StreamingResponse(
        stream_generator(),
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


# ──────────────────────────────────────────────────────────
#  BULK ANALYZE ENDPOINT
# ──────────────────────────────────────────────────────────
@router.post("/bulk", response_model=BulkAnalyzeResponse)
async def bulk_analyze(
    body:    BulkAnalyzeRequest,
    request: Request,
    db:      AsyncSession = Depends(get_db),
):
    """
    Analyze multiple URLs concurrently. Returns results for all.
    Max 20 URLs per request.
    """
    ip = _client_ip(request)

    async def _analyze_one(url: str) -> AnalyzeResponse:
        try:
            validated = validate_url(url)
        except SSRFError as e:
            return AnalyzeResponse(success=False, url=url, error=str(e))
        detection = detect_platform(validated)
        result    = await process_url(detection, quality=body.quality or "best")
        return AnalyzeResponse(
            success=result.success, url=url,
            platform=result.platform, media_type=detection.media_type.value,
            title=result.title, thumbnail=result.thumbnail,
            options=[
                MediaOptionSchema(**{k: getattr(o, k) for k in MediaOptionSchema.model_fields})
                for o in result.options
            ],
            error=result.error,
        )

    results = await asyncio.gather(*[_analyze_one(u) for u in body.urls], return_exceptions=False)
    success_count = sum(1 for r in results if r.success)

    return BulkAnalyzeResponse(
        results=list(results),
        total=len(results),
        success_count=success_count,
        fail_count=len(results) - success_count,
    )
