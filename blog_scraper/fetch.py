from __future__ import annotations

import ipaddress
import time
from urllib.parse import urlparse

import httpx

# Some origins drop connections to cloud datacenter IPs; brief retries
# help transient cases.
_RETRIES = 3
_BACKOFF_SEC = 2.0
_MAX_REDIRECTS = 5
_MAX_RESPONSE_BYTES = 4_000_000


def _host_is_private_or_local(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        ip = ipaddress.ip_address(normalized)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
    except ValueError:
        return False


def fetch_html(url: str, headers: dict[str, str], timeout_seconds: float) -> str:
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise ValueError("fetch_html only supports https URLs")
    host = parsed.hostname or ""
    if _host_is_private_or_local(host):
        raise ValueError("fetch_html target host is private/local and blocked")

    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=_MAX_REDIRECTS,
                headers=headers,
                timeout=timeout_seconds,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                content_len = int(response.headers.get("Content-Length", "0") or "0")
                if content_len > _MAX_RESPONSE_BYTES:
                    raise ValueError("response body too large")
                if len(response.text.encode("utf-8")) > _MAX_RESPONSE_BYTES:
                    raise ValueError("response body too large")
                return response.text
        except (httpx.HTTPError, OSError) as exc:
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_SEC * (attempt + 1))
    assert last is not None
    raise last
