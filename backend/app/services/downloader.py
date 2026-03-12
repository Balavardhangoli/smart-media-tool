"""
services/downloader.py
Main download orchestrator. Routes requests to the correct handler
based on the DetectionResult from detector.py.

Each handler returns a DownloadResult containing either:
  - A direct stream URL
  - A list of media options (for social platforms)
  - An error
"""
import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urljoin

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.services.detector import DetectionResult, Platform, MediaType
from app.utils.file_utils import sanitize_filename, generate_temp_path, extension_from_mime
from app.utils.ssrf_guard import validate_url

logger = get_logger(__name__)

# ── Common HTTP headers (mimic browser) ───────────────────
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


@dataclass
class MediaOption:
    """A single downloadable media item presented to the user."""
    label:      str                    # e.g. "1080p MP4", "MP3 Audio"
    url:        str
    media_type: str                    # image | video | audio | document
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
        max_redirects=settings.max_redirects,
        follow_redirects=True,
        verify=True,
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
        Platform.TIKTOK:    handle_yt_dlp,
        Platform.TWITTER:   handle_yt_dlp,
        Platform.FACEBOOK:  handle_yt_dlp,
        Platform.REDDIT:    handle_reddit,
        Platform.VIMEO:     handle_yt_dlp,
        Platform.PINTEREST: handle_pinterest,
        Platform.WEBPAGE:   handle_webpage,
    }
    handler = handlers.get(detection.platform, handle_webpage)
    try:
        result = await handler(detection, quality=quality)
        result.platform = detection.platform.value
        return result
    except Exception as e:
        logger.error("download_handler_error", platform=detection.platform, error=str(e))
        return DownloadResult(success=False, error=str(e), platform=detection.platform.value)


# ══════════════════════════════════════════════════════════
#  DIRECT FILE HANDLER
# ══════════════════════════════════════════════════════════
async def handle_direct(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Handle direct media file URLs (.jpg, .mp4, .pdf, etc.)."""
    url = detection.url

    async with _make_client() as client:
        # HEAD request to get metadata without downloading
        try:
            head = await client.head(url)
            content_type  = head.headers.get("content-type", "")
            content_length = head.headers.get("content-length")
            file_size = int(content_length) if content_length else None
        except Exception:
            content_type, file_size = "", None

    # Validate file size
    if file_size and file_size > settings.max_file_size_bytes:
        return DownloadResult(
            success=False,
            error=f"File size ({file_size / 1024**2:.1f} MB) exceeds the maximum allowed ({settings.max_file_size_mb} MB).",
        )

    path   = urlparse(url).path
    name   = sanitize_filename(path.split("/")[-1] or "download")
    ext    = extension_from_mime(content_type) or Path(name).suffix
    label  = f"{detection.media_type.value.title()} — {name}"

    return DownloadResult(
        success=True,
        title=name,
        options=[
            MediaOption(
                label=label,
                url=url,
                media_type=detection.media_type.value,
                mime_type=content_type or None,
                file_size=file_size,
                format=ext.lstrip("."),
            )
        ],
    )


# ══════════════════════════════════════════════════════════
#  YOUTUBE HANDLER (via yt-dlp)
# ══════════════════════════════════════════════════════════
async def handle_youtube(detection: DetectionResult, quality: str = "best", **kwargs) -> DownloadResult:
    """Use Cobalt API for YouTube downloads."""
    url = detection.url
    try:
        async with _make_client() as client:
            resp = await client.post(
                "https://api.cobalt.tools/",
                json={
                    "url": url,
                    "videoQuality": "1080",
                    "filenameStyle": "pretty",
                    "downloadMode": "auto",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            data = resp.json()
    except Exception as e:
        return DownloadResult(success=False, error=f"Could not connect to download service: {e}")

    options = []
    status  = data.get("status", "")

    if status == "error":
        code = data.get("error", {}).get("code", "unknown")
        return DownloadResult(success=False, error=f"Download service error: {code}")

    if status in ("redirect", "stream", "tunnel"):
        dl_url = data.get("url")
        if dl_url:
            options.append(MediaOption(
                label="Video — Best Quality (MP4)",
                url=dl_url,
                media_type="video",
                format="mp4",
            ))

    if status == "picker":
        for i, item in enumerate(data.get("picker", [])):
            item_url = item.get("url", "")
            if item_url:
                options.append(MediaOption(
                    label=f"Video Option {i+1}",
                    url=item_url,
                    media_type="video",
                    format="mp4",
                    thumbnail=item.get("thumb"),
                ))

    if not options:
        return DownloadResult(
            success=False,
            error="YouTube blocked this request. Try again in a few seconds.",
        )

    return DownloadResult(
        success=True,
        title="YouTube Video",
        options=options,
    )

# ══════════════════════════════════════════════════════════
#  INSTAGRAM HANDLER
# ══════════════════════════════════════════════════════════
async def handle_instagram(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use Cobalt API for Instagram downloads."""
    url = detection.url
    try:
        async with _make_client() as client:
            resp = await client.post(
                "https://api.cobalt.tools/",
                json={
                    "url": url,
                    "filenameStyle": "pretty",
                    "downloadMode": "auto",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            data = resp.json()
    except Exception as e:
        return DownloadResult(success=False, error=f"Could not connect to download service: {e}")

    options = []
    status  = data.get("status", "")

    if status == "error":
        return DownloadResult(
            success=False,
            error="Instagram post is private or could not be accessed.",
        )

    if status in ("redirect", "stream", "tunnel"):
        dl_url = data.get("url")
        if dl_url:
            options.append(MediaOption(
                label="Instagram Media (Best Quality)",
                url=dl_url,
                media_type="video",
                format="mp4",
            ))

    if status == "picker":
        for i, item in enumerate(data.get("picker", [])):
            item_url = item.get("url", "")
            if item_url:
                options.append(MediaOption(
                    label=f"Media {i+1}",
                    url=item_url,
                    media_type=item.get("type", "video"),
                    format="mp4",
                    thumbnail=item.get("thumb"),
                ))

    if not options:
        return DownloadResult(
            success=False,
            error="Could not extract media. Post may be private or login required.",
        )

    return DownloadResult(
        success=True,
        title="Instagram Post",
        options=options,
    )

    # ── Try extracting from JSON-LD ────────────────────────
    json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
    if json_ld_match:
        try:
            data = json.loads(json_ld_match.group(1))
            if isinstance(data, list): data = data[0]
            title = data.get("name", title)
            # Video
            if "video" in data:
                vids = data["video"] if isinstance(data["video"], list) else [data["video"]]
                for v in vids:
                    content_url = v.get("contentUrl") or v.get("url")
                    if content_url:
                        options.append(MediaOption(
                            label="Video (HD)",
                            url=content_url,
                            media_type="video",
                            thumbnail=v.get("thumbnailUrl"),
                        ))
                        thumbnail = thumbnail or v.get("thumbnailUrl")
            # Image
            if "image" in data and not options:
                imgs = data["image"] if isinstance(data["image"], list) else [data["image"]]
                for img in imgs:
                    img_url = img.get("url") if isinstance(img, dict) else img
                    if img_url:
                        options.append(MediaOption(
                            label="Image (Full Size)",
                            url=img_url,
                            media_type="image",
                            format="jpg",
                        ))
                        thumbnail = thumbnail or img_url
        except Exception:
            pass

    # ── Fallback: parse window.__additionalDataLoaded or shared_data ──
    if not options:
        shared_match = re.search(r'window\.__additionalDataLoaded\s*\(\s*[\'"].*?[\'"]\s*,\s*(\{.*?\})\s*\)', html, re.DOTALL)
        if not shared_match:
            shared_match = re.search(r'<script[^>]*>window\._sharedData\s*=\s*(\{.*?\});</script>', html, re.DOTALL)

        if shared_match:
            try:
                data = json.loads(shared_match.group(1))
                # Walk the nested structure to find media nodes
                _extract_ig_nodes(data, options)
            except Exception:
                pass

    if not options:
        # Cannot parse — provide downloader service links
        shortcode = detection.extra.get("shortcode", "")
        options.append(MediaOption(
            label="Download via SnapInsta",
            url=f"https://snapinsta.app/?url={url}",
            media_type="video",
        ))

    return DownloadResult(
        success=True,
        title=title,
        thumbnail=thumbnail,
        options=options,
    )


def _extract_ig_nodes(data: dict, options: list, depth: int = 0) -> None:
    """Recursively find media URLs in Instagram JSON blobs."""
    if depth > 10:
        return
    if isinstance(data, dict):
        # Video
        if data.get("is_video") and data.get("video_url"):
            options.append(MediaOption(
                label="Video",
                url=data["video_url"],
                media_type="video",
                thumbnail=data.get("display_url"),
            ))
        # Image
        elif data.get("display_url") and not data.get("is_video"):
            options.append(MediaOption(
                label="Image (Full Size)",
                url=data["display_url"],
                media_type="image",
                format="jpg",
            ))
        # Carousel
        if data.get("edge_sidecar_to_children"):
            for edge in data["edge_sidecar_to_children"].get("edges", []):
                _extract_ig_nodes(edge.get("node", {}), options, depth + 1)
        for v in data.values():
            if isinstance(v, (dict, list)):
                _extract_ig_nodes(v, options, depth + 1)
    elif isinstance(data, list):
        for item in data:
            _extract_ig_nodes(item, options, depth + 1)


# ══════════════════════════════════════════════════════════
#  YT-DLP GENERIC HANDLER (TikTok, Twitter, Facebook, Vimeo)
# ══════════════════════════════════════════════════════════
async def handle_yt_dlp(detection: DetectionResult, **kwargs) -> DownloadResult:
    """Use yt-dlp for platforms it supports natively."""
    import yt_dlp

    url = detection.url
    ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    loop = asyncio.get_event_loop()

    def _extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)

    try:
        info = await loop.run_in_executor(None, _extract)
    except Exception as e:
        return DownloadResult(success=False, error=f"Could not extract media info: {e}")

    if not info:
        return DownloadResult(success=False, error="No media found at this URL.")

    title     = info.get("title") or "Media"
    thumbnail = info.get("thumbnail")
    formats   = info.get("formats", [])

    options: List[MediaOption] = []
    for fmt in sorted(formats, key=lambda f: f.get("height") or 0, reverse=True):
        if not fmt.get("url"):
            continue
        h = fmt.get("height")
        label = f"{h}p" if h else fmt.get("format_note", fmt.get("ext", "Media"))
        options.append(MediaOption(
            label=label,
            url=fmt["url"],
            media_type="video",
            mime_type=fmt.get("ext"),
            file_size=fmt.get("filesize"),
            width=fmt.get("width"),
            height=h,
            format=fmt.get("ext", "mp4"),
            thumbnail=thumbnail,
        ))
        if len(options) >= 5:
            break

    return DownloadResult(success=True, title=title, thumbnail=thumbnail, options=options)


# ══════════════════════════════════════════════════════════
#  REDDIT HANDLER
# ══════════════════════════════════════════════════════════
async def handle_reddit(detection: DetectionResult, **kwargs) -> DownloadResult:
    url = detection.url
    json_url = url.rstrip("/") + ".json"

    async with _make_client() as client:
        try:
            resp = await client.get(json_url, headers={**BROWSER_HEADERS, "Accept": "application/json"})
            data = resp.json()
        except Exception as e:
            return DownloadResult(success=False, error=f"Reddit API error: {e}")

    options: List[MediaOption] = []
    title = "Reddit Post"

    try:
        post = data[0]["data"]["children"][0]["data"]
        title = post.get("title", title)

        # Direct video (v.redd.it)
        if post.get("is_video"):
            media = post.get("media", {}).get("reddit_video", {})
            video_url = media.get("fallback_url") or media.get("hls_url")
            if video_url:
                options.append(MediaOption(
                    label=f"Video {media.get('height', '')}p",
                    url=video_url,
                    media_type="video",
                    width=media.get("width"),
                    height=media.get("height"),
                ))

        # Direct image
        if post.get("url", "").endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
            options.append(MediaOption(
                label="Image",
                url=post["url"],
                media_type="image",
                format=post["url"].split(".")[-1],
            ))

        # Gallery
        if post.get("is_gallery"):
            media_meta = post.get("media_metadata", {})
            for item in media_meta.values():
                src = item.get("s", {})
                img_url = src.get("u") or src.get("gif")
                if img_url:
                    options.append(MediaOption(
                        label=f"Image {src.get('x', '')}x{src.get('y', '')}",
                        url=img_url.replace("&amp;", "&"),
                        media_type="image",
                        width=src.get("x"),
                        height=src.get("y"),
                    ))
    except (KeyError, IndexError, TypeError) as e:
        return DownloadResult(success=False, error=f"Could not parse Reddit data: {e}")

    return DownloadResult(success=True, title=title, options=options)


# ══════════════════════════════════════════════════════════
#  PINTEREST HANDLER
# ══════════════════════════════════════════════════════════
async def handle_pinterest(detection: DetectionResult, **kwargs) -> DownloadResult:
    url = detection.url
    async with _make_client() as client:
        try:
            resp = await client.get(url)
            html = resp.text
        except Exception as e:
            return DownloadResult(success=False, error=str(e))

    # Pinterest embeds image URL in og:image
    og_match = re.search(r'<meta property="og:image"\s+content="([^"]+)"', html)
    title_match = re.search(r'<meta property="og:title"\s+content="([^"]+)"', html)

    if og_match:
        img_url = og_match.group(1).replace("236x", "originals").replace("/236x/", "/originals/")
        return DownloadResult(
            success=True,
            title=title_match.group(1) if title_match else "Pinterest Pin",
            thumbnail=og_match.group(1),
            options=[MediaOption(label="Image (Original)", url=img_url, media_type="image", format="jpg")],
        )

    return DownloadResult(success=False, error="Could not extract image from Pinterest pin.")


# ══════════════════════════════════════════════════════════
#  GENERIC WEBPAGE HANDLER
# ══════════════════════════════════════════════════════════
async def handle_webpage(detection: DetectionResult, **kwargs) -> DownloadResult:
    """
    Scrape any webpage for all image/video/audio sources.
    Returns all found media with thumbnails.
    """
    from bs4 import BeautifulSoup

    url = detection.url
    async with _make_client() as client:
        try:
            resp = await client.get(url)
            html = resp.text
            base_url = str(resp.url)
        except Exception as e:
            return DownloadResult(success=False, error=f"Could not fetch page: {e}")

    soup   = BeautifulSoup(html, "lxml")
    options: List[MediaOption] = []
    seen:   set = set()

    # ── Images ────────────────────────────────────────────
    for img in soup.find_all("img", src=True):
        src = urljoin(base_url, img["src"])
        if src in seen or not src.startswith("http"): continue
        seen.add(src)
        try: validate_url(src)
        except Exception: continue
        options.append(MediaOption(
            label=f"Image — {img.get('alt', src.split('/')[-1])[:50]}",
            url=src,
            media_type="image",
            width=int(img.get("width", 0)) or None,
            height=int(img.get("height", 0)) or None,
        ))

    # ── Videos ────────────────────────────────────────────
    for video in soup.find_all("video"):
        for source in video.find_all("source", src=True):
            src = urljoin(base_url, source["src"])
            if src in seen: continue
            seen.add(src)
            try: validate_url(src)
            except Exception: continue
            options.append(MediaOption(
                label=f"Video — {src.split('/')[-1][:50]}",
                url=src,
                media_type="video",
                mime_type=source.get("type"),
            ))

    # ── Audio ─────────────────────────────────────────────
    for audio in soup.find_all("audio"):
        for source in audio.find_all("source", src=True):
            src = urljoin(base_url, source["src"])
            if src in seen: continue
            seen.add(src)
            options.append(MediaOption(
                label=f"Audio — {src.split('/')[-1][:50]}",
                url=src,
                media_type="audio",
                mime_type=source.get("type"),
            ))

    # OG image
    og = soup.find("meta", property="og:image")
    thumbnail = og["content"] if og and og.get("content") else None
    title_tag = soup.find("title")
    title = title_tag.get_text().strip() if title_tag else "Webpage Media"

    if not options:
        return DownloadResult(success=False, error="No downloadable media found on this page.")

    # Limit to 50 items
    return DownloadResult(
        success=True,
        title=title,
        thumbnail=thumbnail,
        options=options[:50],
    )
