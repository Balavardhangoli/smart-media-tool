"""
api/routes/download.py
Download routes: analyze, fetch, bulk.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import get_db
from app.db.models import DownloadHistory
from app.schemas.download import (
    AnalyzeRequest,
    AnalyzeResponse,
    BulkAnalyzeRequest,
    BulkAnalyzeResponse,
    MediaOptionSchema,
)
from app.services.cache import cache_get, cache_set, make_cache_key
from app.services.detector import detect_platform
from app.services.downloader import process_url
from app.utils.ssrf_guard import validate_url, SSRFError

logger = get_logger(__name__)
router = APIRouter(prefix="/download", tags=["download"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


# ══════════════════════════════════════════════════════════
#  ANALYZE
# ══════════════════════════════════════════════════════════
@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    body: AnalyzeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    url = body.url.strip()
    ip  = _client_ip(request)

    # Validate URL
    try:
        validate_url(url)
    except SSRFError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Check cache
    cache_key = make_cache_key("analyze", url)
    cached    = await cache_get(cache_key)
    if cached:
        return AnalyzeResponse(**cached)

    # Detect platform
    detection = detect_platform(url)

    # Process URL
    result = await process_url(detection, quality=body.quality or "best")

    if not result.success:
        raise HTTPException(
            status_code=422,
            detail=result.error or "Could not process this URL.",
        )

    # Build response
    options = [
        MediaOptionSchema(
            label=opt.label,
            url=opt.url,
            media_type=opt.media_type,
            mime_type=opt.mime_type,
            file_size=opt.file_size,
            width=opt.width,
            height=opt.height,
            format=opt.format,
            thumbnail=opt.thumbnail,
        )
        for opt in result.options
    ]

    response = AnalyzeResponse(
        success=True,
        url=url,
        platform=detection.platform.value,
        media_type=detection.media_type.value,
        title=result.title,
        thumbnail=result.thumbnail,
        description=result.description,
        options=options,
    )

    # Cache result
    await cache_set(cache_key, response.dict(), ttl=300)

    # Log to DB
    try:
        entry = DownloadHistory(
            source_url=url,
            media_type=detection.media_type.value,
            platform=detection.platform.value,
            status="completed",
            ip_address=ip,
        )
        db.add(entry)
        await db.commit()
    except Exception as e:
        logger.error(f"db_log_error: {e}")
        await db.rollback()

    return response


# ══════════════════════════════════════════════════════════
#  FETCH (streaming download)
# ══════════════════════════════════════════════════════════
@router.post("/fetch")
async def fetch(
    body: AnalyzeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    url = body.url.strip()

    try:
        validate_url(url)
    except SSRFError as e:
        raise HTTPException(status_code=400, detail=str(e))

    import httpx
    from app.utils.file_utils import sanitize_filename

    url_path = url.split("/")[-1].split("?")[0]
    if url_path and "." in url_path:
        filename = sanitize_filename(url_path)
    else:
        filename = "video.mp4"

    async def stream_file():
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60),
            follow_redirects=True,
        ) as client:
            async with client.stream("GET", url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.instagram.com/",
                "Accept": "*/*",
            }) as response:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    yield chunk

    return StreamingResponse(
        stream_file(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════
#  BULK ANALYZE
# ══════════════════════════════════════════════════════════
@router.post("/bulk", response_model=BulkAnalyzeResponse)
async def bulk_analyze(
    body: BulkAnalyzeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if len(body.urls) > 20:
        raise HTTPException(
            status_code=400,
            detail="Maximum 20 URLs per bulk request.",
        )

    results = []
    for url in body.urls:
        try:
            validate_url(url.strip())
            detection = detect_platform(url.strip())
            result    = await process_url(detection)
            results.append({
                "url":      url,
                "success":  result.success,
                "title":    result.title,
                "platform": detection.platform.value,
                "options":  [
                    {
                        "label":      o.label,
                        "url":        o.url,
                        "media_type": o.media_type,
                        "format":     o.format,
                    }
                    for o in result.options
                ],
                "error": result.error,
            })
        except Exception as e:
            results.append({
                "url":     url,
                "success": False,
                "error":   str(e),
                "options": [],
            })

    success_count = sum(1 for r in results if r["success"])

    return BulkAnalyzeResponse(
        total=len(results),
        success_count=success_count,
        results=results,
    )
