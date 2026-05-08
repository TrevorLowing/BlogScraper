#!/usr/bin/env python3
"""One-shot HTTP GET smoke test (same browser-like headers as blog_scraper.config)."""
from __future__ import annotations

import os
import sys
import time

import httpx

DEFAULT_URL = "https://www.yidaiyilu.gov.cn/list/w/xmzb"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)


def main() -> None:
    url = os.environ.get("TARGET_URL", DEFAULT_URL).strip()
    timeout = float(os.environ.get("HTTP_TIMEOUT_SECONDS", "120"))
    retries = int(os.environ.get("HTTP_RETRIES", "3"))

    headers = {
        "User-Agent": UA,
        "Accept": ACCEPT,
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

    print(f"GET {url}")
    print(f"timeout={timeout}s retries={retries}")

    last_err: BaseException | None = None
    for attempt in range(retries):
        try:
            with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
                r = client.get(url)
            print(f"status={r.status_code} bytes={len(r.content)}")
            preview = r.text[:800].replace("\n", " ")
            print(f"preview={preview!r}")
            if r.status_code >= 400:
                sys.exit(1)
            sys.exit(0)
        except (httpx.HTTPError, OSError) as e:
            last_err = e
            print(f"attempt {attempt + 1}/{retries} error: {type(e).__name__}: {e}")
            if attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))

    print(f"FAILED after {retries} attempts: {last_err}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
