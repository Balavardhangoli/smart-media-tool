"""
utils/ssrf_guard.py
SSRF Prevention - blocks private/internal IPs only.
"""
import ipaddress
import re
import socket
from urllib.parse import urlparse
from typing import Optional

# ── Blocked IP Networks ────────────────────────────────────
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("0.0.0.0/8"),
]

# ── Blocked hostnames ──────────────────────────────────────
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "169.254.169.254",
}

ALLOWED_SCHEMES = {"http", "https"}
MAX_URL_LENGTH = 2048


class SSRFError(ValueError):
    pass


def validate_url(url: str) -> str:
    """Validate URL and block private/internal addresses."""
    if not url or not isinstance(url, str):
        raise SSRFError("URL must be a non-empty string.")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise SSRFError("URL is too long.")

    try:
        parsed = urlparse(url)
    except Exception:
        raise SSRFError("Malformed URL.")

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFError(f"URL scheme '{parsed.scheme}' not allowed. Use http or https.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no valid hostname.")

    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise SSRFError(f"Hostname '{hostname}' is blocked.")

    # Try to resolve hostname - but don't fail if we can't
    try:
        socket.setdefaulttimeout(5)
        addr_infos = socket.getaddrinfo(
            hostname, None,
            socket.AF_UNSPEC,
            socket.SOCK_STREAM
        )
        for addr_info in addr_infos:
            ip_str = addr_info[4][0]
            try:
                ip_obj = ipaddress.ip_address(ip_str)
                for network in BLOCKED_NETWORKS:
                    if ip_obj in network:
                        raise SSRFError(
                            f"Requests to private IP '{ip_str}' are not allowed."
                        )
            except ValueError:
                continue
    except SSRFError:
        raise
    except Exception:
        # If DNS resolution fails for other reasons, allow it
        # and let the actual HTTP request handle the error
        pass

    return url


def is_direct_media_url(url: str) -> Optional[str]:
    """Check if URL points directly to a media file."""
    path = urlparse(url).path.lower().split("?")[0]
    MEDIA_EXTENSIONS = {
        ".jpg": "image", ".jpeg": "image", ".png": "image",
        ".gif": "image", ".webp": "image", ".svg": "image",
        ".bmp": "image", ".tiff": "image", ".avif": "image",
        ".mp4": "video", ".mov": "video", ".webm": "video",
        ".avi": "video", ".mkv": "video", ".m4v": "video",
        ".mp3": "audio", ".wav": "audio", ".ogg": "audio",
        ".flac": "audio", ".aac": "audio", ".m4a": "audio",
        ".pdf": "document", ".doc": "document", ".docx": "document",
        ".zip": "archive", ".tar": "archive", ".gz": "archive",
    }
    for ext, media_type in MEDIA_EXTENSIONS.items():
        if path.endswith(ext):
            return media_type
    return None
