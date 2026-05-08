#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _default_connection_string() -> str:
    return os.environ.get(
        "BLOG_SCRAPER_STORAGE",
        "") or os.environ.get(
        "AzureWebJobsStorage",
        "")


def main() -> int:
    from blog_scraper.downloader import download_recent_posts

    parser = argparse.ArgumentParser(
        description=(
            "Download Chinese + English content for the most recent stored posts."
        ),
    )
    parser.add_argument("--connection-string", default=_default_connection_string())
    parser.add_argument(
        "--container",
        default=os.environ.get(
            "BLOB_CONTAINER_NAME",
            "blog-scraper"))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--output-dir", default="downloads/recent-posts")
    parser.add_argument("--include-raw-html", action="store_true")
    args = parser.parse_args()

    if not args.connection_string.strip():
        print(
            "Missing connection string. Pass --connection-string or set "
            "BLOG_SCRAPER_STORAGE/AzureWebJobsStorage.",
            file=sys.stderr,
        )
        return 2

    summary = download_recent_posts(
        connection_string=args.connection_string,
        container_name=args.container,
        output_dir=args.output_dir,
        limit=args.limit,
        include_raw_html=args.include_raw_html,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
