"""
services/downloader.py
Download orchestrator using yt-dlp (replaces RapidAPI).
Supports: YouTube, Instagram, Facebook, Twitter/X, Reddit, TikTok, direct files.
"""
import asyncio
import os
import re
import tempfile
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
import yt_dlp

from app.core.config import settings
from app.core.logging import get_logger
from app.services.detector import DetectionResult, Platform, MediaType
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

# ── Cookies path (optional - helps with age-restricted / logged-in content) ──
COOKIES_FILE = os.getenv("YTDLP_COOKIES_FILE", "")   # e.g. /app/cookies.txt


# ══════════════════════════════════════════════════════════
#  DATA CLASSES
# ══════════════════════════════════════════════════════════
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
    success:     bool
    options:     List[MediaOption] = field(default_factory=list)
    title:       Optional[str]     = None
    thumbnail:   Optional[str]     = None
    description: Optional[str]     = None
    platform:    Optional[str]     = None
    error:       Optional[str]     = None
    extra:       Dict[str, Any]    = field(default_factory=dict)


def _make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers=BROWSER_HEADERS,
        timeout=httpx.Timeout(30),
        follow_redirects=True,
    )


# ══════════════════════════════════════════════════════════
#  YT-DLP CORE HELPER
# ══════════════════════════════════════════════════════════
def _build_ydl_opts(extra: dict = None) -> dict:
    """Build yt-dlp options. Cookies optional for private/age-restricted content."""
    opts = {
        "quiet":           True,
        "no_warnings":     True,
        "noplaylist":      True,
        "extract_flat":    False,
        "socket_timeout":  20,
        "retries":         3,
        "http_headers":    BROWSER_HEADERS,
        # Don't actually download — just extract info
        "skip_download":   True,
        "format":          "bestvideo+bestaudio/best",
    }
    if COOKIES_FILE and Path(COOKIES_FILE).exists():
        opts["cookiefile"] = COOKIES_FILE
    if extra:
        opts.update(extra)
    return opts


async def _ytdlp_extract(url: str, extra_opts: dict = None) -> DownloadResult:
    """
    Use yt-dlp to extract all available formats from a URL.
    Runs in a thread pool to avoid blocking the event loop.
    """
    def _extract():
        opts = _build_ydl_opts(extra_opts)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await asyncio.get_event_loop().run_in_executor(None, _extract)
    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if "Private video" in msg or "private" in msg.lower():
            return DownloadResult(success=False,
                error="This content is private. Only public content can be downloaded.")
        if "age" in msg.lower() or "sign in" in msg.lower():
            return DownloadResult(success=False,
                error="Age-restricted content. Add cookies to enable this.")
        if "not available" in msg.lower() or "removed" in msg.lower():
            return DownloadResult(success=False,
                error="Content not available. It may have been removed.")
        return DownloadResult(success=False, error=f"Could not extract media: {msg[:200]}")
    except Exception as e:
        return DownloadResult(success=False, error=f"Extraction error: {str(e)[:200]}")

    if not info:
        return DownloadResult(success=False, error="No media info returned.")

    options = _parse_formats(info)

    if not options:
        return DownloadResult(success=False,
            error="No downloadable formats found for this URL.")

    return DownloadResult(
        success=True,
        title=info.get("title") or info.get("fulltitle") or "Video",
        thumbnail=info.get("thumbnail"),
        description=info.get("description", "")[:300] if info.get("description") else None,
        options=options,
    )


def _parse_formats(info: dict) -> List[MediaOption]:
    """Parse yt-dlp format list into MediaOption list."""
    options: List[MediaOption] = []
    seen_labels = set()

    formats = info.get("formats") or []

    # ── Video + Audio combined formats ────────────────────
    video_formats = []
    for f in formats:
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        ext    = f.get("ext", "mp4")
        height = f.get("height") or 0
        fsize  = f.get("filesize") or f.get("filesize_approx") or 0

        # Only include formats with both video and audio (or video-only with note)
        if vcodec == "none":
            continue
        if height < 144:
            continue

        label = f"{height}p {ext.upper()}"
        if label in seen_labels:
            continue
        seen_labels.add(label)

        video_formats.append(MediaOption(
            label=label,
            url=f.get("url", ""),
            media_type="video",
            format=ext,
            file_size=int(fsize) if fsize else None,
            width=f.get("width"),
            height=height,
            thumbnail=info.get("thumbnail"),
        ))

    # Sort by quality descending
    video_formats.sort(key=lambda o: o.height or 0, reverse=True)

    # Deduplicate heights — keep best of each resolution
    seen_heights = set()
    for vf in video_formats:
        if vf.height not in seen_heights:
            seen_heights.add(vf.height)
            if vf.url:
                options.append(vf)

    # ── Audio-only formats ─────────────────────────────────
    audio_formats = []
    for f in formats:
        vcodec = f.get("vcodec", "none")
        acodec = f.get("acodec", "none")
        ext    = f.get("ext", "m4a")
        abr    = f.get("abr") or 0

        if vcodec != "none":
            continue
        if acodec == "none":
            continue
        if ext not in ("mp3", "m4a", "opus", "webm", "ogg"):
            continue

        label = f"{int(abr)}kbps {ext.upper()}" if abr else f"Audio {ext.upper()}"
        if label in seen_labels:
            continue
        seen_labels.add(label)

        fsize = f.get("filesize") or f.get("filesize_approx") or 0
        audio_formats.append(MediaOption(
            label=label,
            url=f.get("url", ""),
            media_type="audio",
            format=ext,
            file_size=int(fsize) if fsize else None,
            thumbnail=info.get("thumbnail"),
        ))

    audio_formats.sort(key=lambda o: int(o.label.split("k")[0]) if "kbps" in o.label else 0, reverse=True)

    # Add top 2 audio options
    for af in audio_formats[:2]:
        if af.url:
            options.append(af)

    return options


# ══════════════════════════════════════════════════════════
#  PLATFORM HANDLERS
# ══════════════════════════════════════════════════════════

async def handle_youtube(detection: DetectionResult, **kwargs) -> DownloadResult:
    """YouTube: use yt-dlp directly."""
    result = await _ytdlp_extract(detection.url)
    if result.success:
        result.title = result.title or "YouTube Video"
    else:
        if not result.error:
            result.error = "Could not download this YouTube video."
    return result


async def handle_instagram(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Instagram: yt-dlp supports Reels, posts, stories."""
    result = await _ytdlp_extract(detection.url)
    if result.success:
        result.title = result.title or "Instagram Post"
    else:
        result.error = (
            result.error or
            "Could not download this Instagram post. "
            "Make sure the account is public."
        )
    return result


async def handle_twitter(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Twitter/X: try both twitter.com and x.com."""
    url = detection.url
    urls_to_try = [url]
    if "x.com" in url:
        urls_to_try.append(url.replace("x.com", "twitter.com"))
    elif "twitter.com" in url:
        urls_to_try.append(url.replace("twitter.com", "x.com"))

    result = DownloadResult(success=False)
    for try_url in urls_to_try:
        result = await _ytdlp_extract(try_url)
        if result.success:
            break

    if result.success:
        result.title = result.title or "Twitter Video"
    else:
        result.error = (
            result.error or
            "Could not download this tweet. Make sure it contains a video "
            "and the account is public."
        )
    return result


async def handle_facebook(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Facebook: yt-dlp supports public videos and reels."""
    url = detection.url
    urls_to_try = [url]
    if "/reel/" in url:
        reel_id = re.search(r"/reel/(\d+)", url)
        if reel_id:
            vid_id = reel_id.group(1)
            urls_to_try.append(f"https://www.facebook.com/watch?v={vid_id}")

    result = DownloadResult(success=False)
    for try_url in urls_to_try:
        result = await _ytdlp_extract(try_url)
        if result.success:
            break

    if result.success:
        result.title = result.title or "Facebook Video"
    else:
        result.error = (
            result.error or
            "Could not download this Facebook video. "
            "Make sure it is public."
        )
    return result


async def handle_reddit(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Reddit: yt-dlp handles v.redd.it videos. Images via JSON API."""
    url = detection.url

    # Handle short Reddit URLs
    if "/s/" in url:
        async with _make_client() as client:
            try:
                resp = await client.get(url, headers=BROWSER_HEADERS)
                url  = str(resp.url).split("?")[0].rstrip("/")
            except Exception:
                pass

    # Try yt-dlp first (works for video posts)
    result = await _ytdlp_extract(url)
    if result.success:
        result.title = result.title or "Reddit Post"
        return result

    # Fallback: Reddit JSON API for images/galleries
    async with _make_client() as client:
        try:
            json_url = url.split("?")[0].rstrip("/") + "/.json"
            resp = await client.get(json_url,
                headers={**BROWSER_HEADERS, "Accept": "application/json"})
            if resp.status_code != 200:
                return DownloadResult(success=False,
                    error="Reddit post not found or private.")
            data = resp.json()
        except Exception as e:
            return DownloadResult(success=False, error=f"Reddit API error: {e}")

    options: List[MediaOption] = []
    title = "Reddit Post"
    try:
        post  = data[0]["data"]["children"][0]["data"]
        title = post.get("title", title)

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
                src = item.get("s", {})
                img_url = (src.get("u") or src.get("gif") or "").replace("&amp;", "&")
                if img_url:
                    options.append(MediaOption(
                        label=f"Image {src.get('x','')}x{src.get('y','')}",
                        url=img_url,
                        media_type="image",
                        width=src.get("x"),
                        height=src.get("y"),
                    ))
    except (KeyError, IndexError, TypeError) as e:
        return DownloadResult(success=False,
            error=f"Could not parse Reddit post: {e}")

    if not options:
        return DownloadResult(success=False,
            error="No downloadable media found in this Reddit post.")

    return DownloadResult(success=True, title=title, options=options)


async def handle_tiktok(detection: DetectionResult, **kwargs) -> DownloadResult:
    """TikTok: yt-dlp handles watermark-free downloads."""
    result = await _ytdlp_extract(detection.url, extra_opts={
        "extractor_args": {"tiktok": {"api_hostname": "api22-normal-c-useast2a.tiktokv.com"}}
    })
    if result.success:
        result.title = result.title or "TikTok Video"
    else:
        result.error = result.error or "Could not download this TikTok video."
    return result


async def handle_direct(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Direct file URLs — image, video, audio, PDF."""
    url = detection.url
    ext = url.split("?")[0].split(".")[-1].lower()
    media_type = (
        "image"    if ext in ("jpg", "jpeg", "png", "gif", "webp", "svg") else
        "audio"    if ext in ("mp3", "wav", "ogg", "flac", "aac", "m4a") else
        "document" if ext in ("pdf", "doc", "docx")                        else
        "video"
    )
    async with _make_client() as client:
        try:
            head = await client.head(url)
            fsize = int(head.headers.get("content-length", 0)) or None
        except Exception:
            fsize = None

    label = ext.upper() if ext else "File"
    return DownloadResult(
        success=True,
        title=url.split("/")[-1].split("?")[0] or "Direct File",
        options=[MediaOption(
            label=label,
            url=url,
            media_type=media_type,
            format=ext,
            file_size=fsize,
        )],
    )


# ══════════════════════════════════════════════════════════
#  ORCHESTRATOR
# ══════════════════════════════════════════════════════════
_HANDLERS = {
    Platform.YOUTUBE:   handle_youtube,
    Platform.INSTAGRAM: handle_instagram,
    Platform.TWITTER:   handle_twitter,
    Platform.FACEBOOK:  handle_facebook,
    Platform.REDDIT:    handle_reddit,
    Platform.TIKTOK:    handle_tiktok,
}

async def process_url(detection: DetectionResult, quality: str = "best") -> DownloadResult:
    """Route URL to correct handler based on detected platform."""
    handler = _HANDLERS.get(detection.platform)
    if handler:
        try:
            result = await handler(detection)
            if result.success:
                logger.info(f"download_success: platform={detection.platform.value} "
                            f"options={len(result.options)}")
            else:
                logger.warning(f"download_failed: platform={detection.platform.value} "
                               f"error={result.error}")
            return result
        except Exception as e:
            logger.error(f"handler_error: platform={detection.platform.value} error={e}")
            return DownloadResult(success=False,
                error=f"Could not process this URL. Please try again.")

    # Unknown platform — try yt-dlp anyway (covers 1000+ sites)
    result = await _ytdlp_extract(detection.url)
    if not result.success:
        # Last resort: direct file
        return await handle_direct(detection)
    return result
