from __future__ import annotations

import time

import httpx

# Some origins drop connections to cloud datacenter IPs; brief retries help transient cases.
_RETRIES = 3
_BACKOFF_SEC = 2.0


def fetch_html(url: str, headers: dict[str, str], timeout_seconds: float) -> str:
    last: Exception | None = None
    for attempt in range(_RETRIES):
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout_seconds) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except (httpx.HTTPError, OSError) as exc:
            last = exc
            if attempt < _RETRIES - 1:
                time.sleep(_BACKOFF_SEC * (attempt + 1))
    assert last is not None
    raise last
