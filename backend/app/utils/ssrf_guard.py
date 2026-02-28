"""
utils/ssrf_guard.py
SSRF (Server-Side Request Forgery) Prevention.

Blocks requests to:
  - Private IP ranges (RFC 1918)
  - Loopback addresses
  - Link-local addresses
  - Cloud metadata endpoints (AWS, GCP, Azure)
  - Internal hostnames
"""
import ipaddress
import re
import socket
from urllib.parse import urlparse
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Blocked IP Networks ────────────────────────────────────
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),        # Private
    ipaddress.ip_network("172.16.0.0/12"),      # Private
    ipaddress.ip_network("192.168.0.0/16"),     # Private
    ipaddress.ip_network("127.0.0.0/8"),        # Loopback
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),     # Link-local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),          # "This" network
    ipaddress.ip_network("100.64.0.0/10"),      # Shared address space
    ipaddress.ip_network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.ip_network("198.18.0.0/15"),      # Benchmark Testing
    ipaddress.ip_network("198.51.100.0/24"),    # Documentation
    ipaddress.ip_network("203.0.113.0/24"),     # Documentation
    ipaddress.ip_network("240.0.0.0/4"),        # Reserved
]

# ── Blocked hostnames / patterns ───────────────────────────
BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",         # GCP metadata
    "169.254.169.254",                   # AWS/GCP/Azure metadata IP
}

BLOCKED_HOSTNAME_PATTERNS = [
    re.compile(r"^.*\.internal$"),
    re.compile(r"^.*\.local$"),
    re.compile(r"^.*\.localhost$"),
]

# ── Allowed schemes ────────────────────────────────────────
ALLOWED_SCHEMES = {"http", "https"}

# ── Max URL length ─────────────────────────────────────────
MAX_URL_LENGTH = 2048


class SSRFError(ValueError):
    """Raised when a URL fails SSRF validation."""
    pass


def validate_url(url: str) -> str:
    """
    Validate and sanitize a URL. Returns the cleaned URL or raises SSRFError.

    Steps:
    1. Length check
    2. Scheme check (only http/https)
    3. Parse URL
    4. Resolve hostname to IP
    5. Check IP against blocked networks
    6. Check hostname against block list
    """
    if not url or not isinstance(url, str):
        raise SSRFError("URL must be a non-empty string.")

    url = url.strip()

    if len(url) > MAX_URL_LENGTH:
        raise SSRFError(f"URL exceeds maximum allowed length of {MAX_URL_LENGTH} characters.")

    # Parse
    try:
        parsed = urlparse(url)
    except Exception:
        raise SSRFError("Malformed URL.")

    # Scheme check
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise SSRFError(f"URL scheme '{parsed.scheme}' is not allowed. Use http or https.")

    # Must have a hostname
    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("URL has no valid hostname.")

    # Hostname blocklist check
    if hostname.lower() in BLOCKED_HOSTNAMES:
        raise SSRFError(f"Hostname '{hostname}' is blocked.")

    for pattern in BLOCKED_HOSTNAME_PATTERNS:
        if pattern.match(hostname.lower()):
            raise SSRFError(f"Hostname '{hostname}' matches a blocked pattern.")

    # Resolve hostname to IP and check against blocked networks
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise SSRFError(f"Cannot resolve hostname '{hostname}'.")

    for addr_info in addr_infos:
        ip_str = addr_info[4][0]
        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        for network in BLOCKED_NETWORKS:
            if ip_obj in network:
                logger.warning("ssrf_blocked", url=url, ip=ip_str, network=str(network))
                raise SSRFError(
                    f"Requests to IP address '{ip_str}' are not allowed (private/reserved range)."
                )

    logger.debug("url_validated", url=url, hostname=hostname)
    return url


def is_direct_media_url(url: str) -> Optional[str]:
    """
    Check if URL points directly to a downloadable media file.
    Returns the detected extension, or None.
    """
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
