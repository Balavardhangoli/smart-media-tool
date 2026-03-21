"""
services/detector.py
Detect the platform and media type of a given URL.
Returns a structured DetectionResult used by download handlers.
"""
import re
from dataclasses import dataclass, field
from enum import Enum
from urllib.parse import urlparse
from typing import Optional

from app.utils.ssrf_guard import is_direct_media_url


class Platform(str, Enum):
    YOUTUBE    = "youtube"
    INSTAGRAM  = "instagram"
    TIKTOK     = "tiktok"
    TWITTER    = "twitter"
    FACEBOOK   = "facebook"
    REDDIT     = "reddit"
    VIMEO      = "vimeo"
    PINTEREST  = "pinterest"
    DIRECT     = "direct"
    WEBPAGE    = "webpage"
    UNKNOWN    = "unknown"


class MediaType(str, Enum):
    IMAGE    = "image"
    VIDEO    = "video"
    AUDIO    = "audio"
    DOCUMENT = "document"
    WEBPAGE  = "webpage"
    UNKNOWN  = "unknown"


@dataclass
class DetectionResult:
    url:        str
    platform:   Platform
    media_type: MediaType
    video_id:   Optional[str] = None
    extra:      dict          = field(default_factory=dict)


# ── Platform patterns ──────────────────────────────────────
YOUTUBE_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})"),
]

INSTAGRAM_PATTERNS = [
    re.compile(r"instagram\.com/(p|reel|stories)/([^/?#]+)"),
]

TIKTOK_PATTERNS = [
    re.compile(r"(?:tiktok\.com|vm\.tiktok\.com)"),
]

TWITTER_PATTERNS = [
    re.compile(r"(?:twitter\.com|x\.com)/\w+/status/(\d+)"),
]

FACEBOOK_PATTERNS = [
    re.compile(r"(?:facebook\.com|fb\.com|fb\.watch)"),
]

REDDIT_PATTERNS = [
    re.compile(r"(?:reddit\.com|redd\.it|v\.redd\.it|i\.redd\.it)"),
]

VIMEO_PATTERNS = [
    re.compile(r"vimeo\.com/(\d+)"),
]

PINTEREST_PATTERNS = [
    re.compile(r"(?:pinterest\.com|pin\.it)"),
]


def detect_platform(url: str) -> DetectionResult:
    """
    Analyze a URL and return a DetectionResult with platform, media type,
    and any extracted identifiers (e.g. video ID).
    """
    # 1. Direct media file?
    direct_type = is_direct_media_url(url)
    if direct_type:
        return DetectionResult(
            url=url,
            platform=Platform.DIRECT,
            media_type=MediaType(direct_type),
        )

    parsed = urlparse(url)
    host   = parsed.netloc.lower().replace("www.", "")

    # 2. YouTube
    for pat in YOUTUBE_PATTERNS:
        m = pat.search(url)
        if m:
            return DetectionResult(
                url=url,
                platform=Platform.YOUTUBE,
                media_type=MediaType.VIDEO,
                video_id=m.group(1),
            )

    # 3. Instagram
    for pat in INSTAGRAM_PATTERNS:
        m = pat.search(url)
        if m:
            kind = m.group(1)
            return DetectionResult(
                url=url,
                platform=Platform.INSTAGRAM,
                media_type=MediaType.VIDEO if kind == "reel" else MediaType.IMAGE,
                extra={"kind": kind, "shortcode": m.group(2)},
            )

   
    # 5. Twitter
    for pat in TWITTER_PATTERNS:
        m = pat.search(url)
        if m:
            return DetectionResult(
                url=url,
                platform=Platform.TWITTER,
                media_type=MediaType.VIDEO,
                video_id=m.group(1),
            )

    # 6. Facebook
    if any(pat.search(url) for pat in FACEBOOK_PATTERNS):
        return DetectionResult(url=url, platform=Platform.FACEBOOK, media_type=MediaType.VIDEO)

    # 7. Reddit
    if any(pat.search(url) for pat in REDDIT_PATTERNS):
        return DetectionResult(url=url, platform=Platform.REDDIT, media_type=MediaType.VIDEO)

    # 10. Generic webpage — will be scraped for media
    return DetectionResult(url=url, platform=Platform.WEBPAGE, media_type=MediaType.WEBPAGE)
