"""
services/downloader.py
Main download orchestrator using RapidAPI Snap Video.
"""
import asyncio
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urljoin

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.detector import DetectionResult, Platform, MediaType
from app.utils.file_utils import sanitize_filename, extension_from_mime
from app.utils.ssrf_guard import validate_url

logger = get_logger(__name__)

# ── Common HTTP headers ────────────────────────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── RapidAPI Config ────────────────────────────────────────
RAPIDAPI_KEY  = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = os.getenv("RAPIDAPI_HOST", "snap-video3.p.rapidapi.com")
RAPIDAPI_URL  = f"https://{RAPIDAPI_HOST}/download"


@dataclass
class MediaOption:
    label:      str
    url:        str
    media_type: str
    mime_type:  Optional[str] = None
    file_size:  Optional[int] = None
    width:      Optional[int] = None
    height:     Optional[int] = None
    format:     Optional[str] = None
    thumbnail:  Optional[str] = None


@dataclass
class DownloadResult:
    success:      bool
    options:      List[MediaOption] = field(default_factory=list)
    title:        Optional[str]     = None
    thumbnail:    Optional[str]     = None
    description:  Optional[str]     = None
    platform:     Optional[str]     = None
    error:        Optional[str]     = None
    extra:        Dict[str, Any]    = field(default_factory=dict)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=BROWSER_HEADERS,
        timeout=httpx.Timeout(settings.http_timeout_seconds),
        follow_redirects=True,
        verify=True,
    )


# ══════════════════════════════════════════════════════════
#  RAPIDAPI SNAP VIDEO HELPER
# ══════════════════════════════════════════════════════════
async def _rapidapi_download(url: str) -> DownloadResult:
    """Use RapidAPI Snap Video to download from YouTube, Instagram, TikTok etc."""
    if not RAPIDAPI_KEY:
        return DownloadResult(
            success=False,
            error="API key not configured. Please add RAPIDAPI_KEY to environment.",
        )

    headers = {
        "x-rapidapi-host": RAPIDAPI_HOST,
        "x-rapidapi-key": RAPIDAPI_KEY,
    }

    # Clean URL - remove extra spaces and trailing slashes
    clean_url = url.strip().rstrip("/")

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(30),
            follow_redirects=True,
        ) as client:
            resp = await client.post(
                RAPIDAPI_URL,
                data={"url": clean_url},
                headers=headers,
            )
            data = resp.json()
            logger.info(f"rapidapi_response: {data}")
    except Exception as e:
        return DownloadResult(success=False, error=f"API request failed: {str(e)}")

    if resp.status_code != 200:
        return DownloadResult(
            success=False,
            error=f"Download service error (HTTP {resp.status_code})",
        )

    options = []

    # Use medias array — skip the top-level url field (it points back to YouTube)
    if data.get("medias"):
        for i, item in enumerate(data["medias"]):
            item_url = item.get("url") or item.get("videoUrl")
            if not item_url:
                continue
            quality   = item.get("quality", "") or f"Option {i+1}"
            extension = item.get("extension", "mp4").lower()
            size      = item.get("size") or 0

            # Skip items with size 0 unless it is the only option
            # (size 0 means server-side merge required — may not download correctly)
            media_type = "audio" if extension in ("mp3", "m4a", "ogg", "wav") else "video"

            options.append(MediaOption(
                label=f"{quality} {extension.upper()}",
                url=item_url,
                media_type=media_type,
                format=extension,
                file_size=size if size > 0 else None,
                thumbnail=data.get("thumbnail"),
            ))

    # Sort: real video files (size > 0) first
    options.sort(key=lambda o: (o.file_size or 0), reverse=True)

    if not options:
        return DownloadResult(
            success=False,
            error="No downloadable media found. The content may be private.",
        )

    title     = data.get("title") or data.get("name") or "Video"
    thumbnail = data.get("thumbnail") or data.get("thumb")

    return DownloadResult(
        success=True,
        title=title,
        thumbnail=thumbnail,
        options=options,
    )


# ══════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════
async def process_url(detection: DetectionResult, quality: str = "best") -> DownloadResult:
    """Route to the correct handler based on detected platform."""
    handlers = {
        Platform.DIRECT:    handle_direct,
        Platform.YOUTUBE:   handle_youtube,
        Platform.INSTAGRAM: handle_instagram,
        Platform.TIKTOK:    handle_tiktok,
        Platform.TWITTER:   handle_twitter,
        Platform.FACEBOOK:  handle_facebook,
        Platform.REDDIT:    handle_reddit,
        Platform.VIMEO:     handle_vimeo,
        Platform.PINTEREST: handle_pinterest,
        Platform.WEBPAGE:   handle_webpage,
    }
    handler = handlers.get(detection.platform, handle_webpage)
    try:
        result = await handler(detection, quality=quality)
        result.platform = detection.platform.value
        return result
    except Exception as e:
        logger.error("download_handler_error",
                     platform=detection.platform, error=str(e))
        return DownloadResult(
            success=False,
            error=f"An error occurred: {str(e)}",
            platform=detection.platform.value,
        )


# ══════════════════════════════════════════════════════════
#  DIRECT FILE HANDLER
# ══════════════════════════════════════════════════════════
async def handle_direct(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Handle direct media file URLs (.jpg, .mp4, .pdf, etc.)."""
    url = detection.url

    try:
        async with _make_client() as client:
            head = await client.head(url)
            content_type   = head.headers.get("content-type", "application/octet-stream")
            content_length = head.headers.get("content-length")
            file_size = int(content_length) if content_length else None
    except Exception:
        content_type = "application/octet-stream"
        file_size    = None

    if file_size and file_size > settings.max_file_size_bytes:
        return DownloadResult(
            success=False,
            error=f"File too large. Max: {settings.max_file_size_mb} MB",
        )

    path = urlparse(url).path
    name = sanitize_filename(path.split("/")[-1] or "download")
    ext  = Path(name).suffix or ".bin"

    return DownloadResult(
        success=True,
        title=name,
        options=[
            MediaOption(
                label=f"Download {ext.upper().lstrip('.')} — {name}",
                url=url,
                media_type=detection.media_type.value,
                mime_type=content_type,
                file_size=file_size,
                format=ext.lstrip("."),
            )
        ],
    )


# ══════════════════════════════════════════════════════════
#  YOUTUBE
# ══════════════════════════════════════════════════════════
async def handle_youtube(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use RapidAPI for YouTube downloads."""
    result = await _rapidapi_download(detection.url)
    if result.success:
        result.title = result.title or "YouTube Video"
    return result


# ══════════════════════════════════════════════════════════
#  INSTAGRAM
# ══════════════════════════════════════════════════════════
async def handle_instagram(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use RapidAPI for Instagram downloads."""
    result = await _rapidapi_download(detection.url)
    if result.success:
        result.title = result.title or "Instagram Post"
    else:
        # Give more helpful error messages for Instagram
        if result.error and "private" in result.error.lower():
            result.error = "This Instagram account is private. Only public posts can be downloaded."
        elif result.error and ("not found" in result.error.lower() or "404" in result.error):
            result.error = "Instagram post not found. It may have been deleted."
        elif result.error and "429" in result.error:
            result.error = "Too many requests. Please wait a moment and try again."
        elif not result.options:
            result.error = "Could not download this Instagram post. It may be private, deleted, or a live video."
    return result


# ══════════════════════════════════════════════════════════
#  TIKTOK
# ══════════════════════════════════════════════════════════
async def handle_tiktok(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use RapidAPI for TikTok downloads."""
    result = await _rapidapi_download(detection.url)
    if result.success:
        result.title = result.title or "TikTok Video"
    return result


# ══════════════════════════════════════════════════════════
#  TWITTER
# ══════════════════════════════════════════════════════════
async def handle_twitter(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use RapidAPI for Twitter/X downloads."""
    result = await _rapidapi_download(detection.url)
    if result.success:
        result.title = result.title or "Twitter Video"
    return result


# ══════════════════════════════════════════════════════════
#  FACEBOOK
# ══════════════════════════════════════════════════════════
async def handle_facebook(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use RapidAPI for Facebook downloads."""
    result = await _rapidapi_download(detection.url)
    if result.success:
        result.title = result.title or "Facebook Video"
    return result


# ══════════════════════════════════════════════════════════
#  VIMEO
# ══════════════════════════════════════════════════════════
async def handle_vimeo(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use RapidAPI for Vimeo downloads."""
    result = await _rapidapi_download(detection.url)
    if result.success:
        result.title = result.title or "Vimeo Video"
    return result


# ══════════════════════════════════════════════════════════
#  REDDIT
# ══════════════════════════════════════════════════════════
async def handle_reddit(detection: DetectionResult, **kwargs) -> DownloadResult:
    url      = detection.url
    json_url = url.rstrip("/") + ".json"

    async with _make_client() as client:
        try:
            resp = await client.get(
                json_url,
                headers={**BROWSER_HEADERS, "Accept": "application/json"},
            )
            data = resp.json()
        except Exception as e:
            return DownloadResult(success=False, error=f"Reddit API error: {e}")

    options: List[MediaOption] = []
    title = "Reddit Post"

    try:
        post  = data[0]["data"]["children"][0]["data"]
        title = post.get("title", title)

        if post.get("is_video"):
            media     = post.get("media", {}).get("reddit_video", {})
            video_url = media.get("fallback_url") or media.get("hls_url")
            if video_url:
                options.append(MediaOption(
                    label=f"Video {media.get('height', '')}p",
                    url=video_url,
                    media_type="video",
                    width=media.get("width"),
                    height=media.get("height"),
                ))

        if post.get("url", "").endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
            options.append(MediaOption(
                label="Image",
                url=post["url"],
                media_type="image",
                format=post["url"].split(".")[-1],
            ))

        if post.get("is_gallery"):
            media_meta = post.get("media_metadata", {})
            for item in media_meta.values():
                src     = item.get("s", {})
                img_url = src.get("u") or src.get("gif")
                if img_url:
                    options.append(MediaOption(
                        label=f"Image {src.get('x','')}x{src.get('y','')}",
                        url=img_url.replace("&amp;", "&"),
                        media_type="image",
                        width=src.get("x"),
                        height=src.get("y"),
                    ))
    except (KeyError, IndexError, TypeError) as e:
        return DownloadResult(success=False, error=f"Could not parse Reddit data: {e}")

    return DownloadResult(success=True, title=title, options=options)


# ══════════════════════════════════════════════════════════
#  PINTEREST
# ══════════════════════════════════════════════════════════
async def handle_pinterest(detection: DetectionResult, **kwargs) -> DownloadResult:
    url = detection.url
    async with _make_client() as client:
        try:
            resp = await client.get(url)
            html = resp.text
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    og_match    = re.search(r'<meta property="og:image"\s+content="([^"]+)"', html)
    title_match = re.search(r'<meta property="og:title"\s+content="([^"]+)"', html)

    if og_match:
        img_url = og_match.group(1).replace("236x", "originals")
        return DownloadResult(
            success=True,
            title=title_match.group(1) if title_match else "Pinterest Pin",
            thumbnail=og_match.group(1),
            options=[MediaOption(
                label="Image (Original)",
                url=img_url,
                media_type="image",
                format="jpg",
            )],
        )

    return DownloadResult(success=False, error="Could not extract image from Pinterest.")


# ══════════════════════════════════════════════════════════
#  GENERIC WEBPAGE
# ══════════════════════════════════════════════════════════
async def handle_webpage(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Scrape any webpage for all image/video/audio sources."""
    from bs4 import BeautifulSoup

    url = detection.url
    async with _make_client() as client:
        try:
            resp     = await client.get(url)
            html     = resp.text
            base_url = str(resp.url)
        except Exception as e:
            return DownloadResult(success=False, error=f"Could not fetch page: {e}")

    soup    = BeautifulSoup(html, "lxml")
    options: List[MediaOption] = []
    seen:   set = set()

    for img in soup.find_all("img", src=True):
        src = urljoin(base_url, img["src"])
        if src in seen or not src.startswith("http"):
            continue
        seen.add(src)
        try:
            validate_url(src)
        except Exception:
            continue
        options.append(MediaOption(
            label=f"Image — {img.get('alt', src.split('/')[-1])[:50]}",
            url=src,
            media_type="image",
            width=int(img.get("width", 0)) or None,
            height=int(img.get("height", 0)) or None,
        ))

    for video in soup.find_all("video"):
        for source in video.find_all("source", src=True):
            src = urljoin(base_url, source["src"])
            if src in seen:
                continue
            seen.add(src)
            try:
                validate_url(src)
            except Exception:
                continue
            options.append(MediaOption(
                label=f"Video — {src.split('/')[-1][:50]}",
                url=src,
                media_type="video",
                mime_type=source.get("type"),
            ))

    og        = soup.find("meta", property="og:image")
    thumbnail = og["content"] if og and og.get("content") else None
    title_tag = soup.find("title")
    title     = title_tag.get_text().strip() if title_tag else "Webpage Media"

    if not options:
        return DownloadResult(
            success=False,
            error="No downloadable media found on this page.",
        )

    return DownloadResult(
        success=True,
        title=title,
        thumbnail=thumbnail,
        options=options[:50],
    )
