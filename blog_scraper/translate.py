from __future__ import annotations

import time
from typing import Any

import httpx

from blog_scraper.config import BlogScraperConfig

_TRANSLATE_PATH = "/translate"
_RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 4
_BASE_BACKOFF_SECONDS = 1.0


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    raw = resp.headers.get("Retry-After", "").strip()
    if not raw:
        return None
    try:
        secs = float(raw)
        return secs if secs >= 0 else None
    except ValueError:
        return None


def translate_zh_fragment_to_en(text: str, cfg: BlogScraperConfig) -> str:
    """
    Translate zh-Hans/HTML-ish fragment to English.

    Without ``TRANSLATOR_KEY`` returns a prefixed stub suitable for offline tests.
    """
    stripped = text.strip()
    if not stripped:
        return ""

    if not cfg.translator_key.strip() or not cfg.translator_endpoint.strip():
        return "[STUB_TRANSLATION_ZH→EN]\n" + stripped

    endpoint = cfg.translator_endpoint.rstrip("/") + _TRANSLATE_PATH
    params = {"api-version": "3.0", "from": "zh-Hans", "to": "en"}
    # stay under Translator limits per item
    body: list[dict[str, Any]] = [{"text": stripped[:49000]}]

    hdrs = {
        "Ocp-Apim-Subscription-Key": cfg.translator_key,
        "Content-Type": "application/json",
    }
    if cfg.translator_region.strip():
        hdrs["Ocp-Apim-Subscription-Region"] = cfg.translator_region.strip()

    with httpx.Client(timeout=120.0) as client:
        last_error: httpx.HTTPStatusError | None = None
        payload: list[dict[str, Any]] = []
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            r = client.post(endpoint, params=params, headers=hdrs, json=body)
            try:
                r.raise_for_status()
                payload = r.json()
                break
            except httpx.HTTPStatusError as exc:
                if (
                    r.status_code not in _RETRYABLE_STATUS_CODES
                    or attempt >= _MAX_ATTEMPTS
                ):
                    raise
                last_error = exc
                retry_after = _retry_after_seconds(r)
                if retry_after is None:
                    retry_after = _BASE_BACKOFF_SECONDS * (2 ** (attempt - 1))
                time.sleep(retry_after)
        if last_error and not payload:
            raise last_error

    out_parts: list[str] = []
    for item in payload:
        for tr in item.get("translations", []):
            t = tr.get("text")
            if t:
                out_parts.append(t)
    return "\n".join(out_parts) if out_parts else stripped
