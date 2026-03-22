"""
api/routes/download.py
Download routes: analyze, fetch, bulk.
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

_limiter = Limiter(key_func=get_remote_address)
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

    # Block javascript: and data: URLs
    if url.lower().startswith(('javascript:', 'data:', 'vbscript:', 'file:')):
        raise HTTPException(status_code=400, detail="URL scheme not allowed.")

    import httpx
    from app.utils.file_utils import sanitize_filename

    # ── Smart filename + MIME detection ──────────────────
    MIME_TO_EXT = {
        "video/mp4":        ".mp4",
        "video/webm":       ".webm",
        "video/quicktime":  ".mov",
        "video/x-matroska": ".mkv",
        "audio/mpeg":       ".mp3",
        "audio/mp4":        ".m4a",
        "audio/ogg":        ".ogg",
        "audio/wav":        ".wav",
        "image/jpeg":       ".jpg",
        "image/png":        ".png",
        "image/gif":        ".gif",
        "image/webp":       ".webp",
        "image/svg+xml":    ".svg",
        "application/pdf":  ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/zip":  ".zip",
        "text/plain":       ".txt",
        "text/html":        ".html",
    }

    MIME_TO_MEDIA = {
        "video": "video/mp4",
        "audio": "audio/mpeg",
        "image": "image/jpeg",
        "document": "application/octet-stream",
    }

    async def get_filename_and_mime(download_url: str):
        """HEAD request to detect real content type and filename."""
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(10),
                follow_redirects=True,
            ) as client:
                head = await client.head(download_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Referer": "https://www.instagram.com/",
                })
                content_type = head.headers.get("content-type", "").split(";")[0].strip()
                content_disp = head.headers.get("content-disposition", "")

                # Try to get filename from content-disposition header
                fname = None
                if "filename=" in content_disp:
                    fname = content_disp.split("filename=")[-1].strip().strip('"')

                # Get extension from content-type
                ext = MIME_TO_EXT.get(content_type, "")

                # Get extension from URL path
                url_path = download_url.split("/")[-1].split("?")[0]
                url_ext  = "." + url_path.split(".")[-1].lower() if "." in url_path else ""

                # Decide filename
                if fname:
                    final_name = sanitize_filename(fname)
                    if ext and not final_name.endswith(ext):
                        final_name += ext
                elif url_ext and url_ext in MIME_TO_EXT.values():
                    final_name = sanitize_filename(url_path) if url_path else f"download{url_ext}"
                elif ext:
                    final_name = f"download{ext}"
                else:
                    final_name = "download.mp4"

                return final_name, content_type or "application/octet-stream"
        except Exception:
            # Fallback: guess from URL
            url_path = download_url.split("/")[-1].split("?")[0]
            if url_path and "." in url_path:
                return sanitize_filename(url_path), "application/octet-stream"
            return "download.mp4", "application/octet-stream"

    filename, mime_type = await get_filename_and_mime(url)

    # Download full file first to verify it is valid
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60),
            follow_redirects=True,
        ) as client:
            response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.instagram.com/",
                "Accept": "*/*",
            })

            if response.status_code != 200:
                raise HTTPException(
                    status_code=400,
                    detail=f"Source server returned error {response.status_code}. Cannot download this file."
                )

            # Use content-type from actual response if available
            actual_content_type = response.headers.get("content-type", "").split(";")[0].strip()
            if actual_content_type and actual_content_type != "text/html":
                mime_type = actual_content_type
                # Fix filename extension based on actual content type
                actual_ext = MIME_TO_EXT.get(actual_content_type, "")
                if actual_ext:
                    base = filename.rsplit(".", 1)[0] if "." in filename else filename
                    filename = base + actual_ext

            file_content = response.content

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not download file: {str(e)}")

    from fastapi.responses import Response
    return Response(
        content=file_content,
        media_type=mime_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ══════════════════════════════════════════════════════════
#  BULK ANALYZE
# ══════════════════════════════════════════════════════════
@router.post("/bulk", response_model=BulkAnalyzeResponse)
@_limiter.limit("5/minute")
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

    # Deduplicate URLs
    seen = set()
    unique_urls = []
    for url in body.urls:
        clean = url.strip()
        if clean and clean not in seen:
            seen.add(clean)
            unique_urls.append(clean)

    # Process all URLs concurrently for speed
    async def process_single(url: str) -> dict:
        try:
            validate_url(url)
            if url.lower().startswith(('javascript:', 'data:', 'vbscript:', 'file:')):
                raise ValueError("URL scheme not allowed.")
            detection = detect_platform(url)
            # 25 second timeout per URL
            result = await asyncio.wait_for(process_url(detection), timeout=25.0)
            return {
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
                        "file_size":  o.file_size or 0,
                    }
                    for o in result.options
                ],
                "error": result.error,
            }
        except asyncio.TimeoutError:
            return {
                "url":     url,
                "success": False,
                "error":   "Request timed out. URL may be slow or unavailable.",
                "options": [],
            }
        except Exception as e:
            return {
                "url":     url,
                "success": False,
                "error":   str(e),
                "options": [],
            }

    # Process sequentially with small delay to avoid RapidAPI rate limits
    # (RapidAPI free plan: 5 req/second — concurrent calls risk 429 errors)
    results = []
    for i, url in enumerate(unique_urls):
        result = await process_single(url)
        results.append(result)
        # Add 0.4s delay between calls to stay within RapidAPI rate limit
        # Skip delay after last URL
        if i < len(unique_urls) - 1:
            await asyncio.sleep(0.4)

    success_count = sum(1 for r in results if r["success"])

    return BulkAnalyzeResponse(
        total=len(results),
        success_count=success_count,
        results=results,
    )
