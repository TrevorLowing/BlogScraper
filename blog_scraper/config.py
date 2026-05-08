from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


# Browser-like defaults for outbound HTTP (Azure Functions otherwise send
# a sparse header set).
DEFAULT_HTTP_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
DEFAULT_ACCEPT = (
    "text/html,application/xhtml+xml,application/xml;q=0.9,"
    "image/avif,image/webp,image/apng,*/*;q=0.8"
)
DEFAULT_ACCEPT_LANGUAGE = "en-US,en;q=0.9"
DEFAULT_REFERER = "https://www.google.com/"


def _parse_csv_urls(value: str) -> tuple[str, ...]:
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return tuple(parts)


def _parse_headers_json(raw: str) -> dict[str, str]:
    if not raw.strip():
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("HTTP_EXTRA_HEADERS_JSON must be a JSON object")
    out: dict[str, str] = {}
    for k, v in data.items():
        if v is None:
            continue
        out[str(k)] = str(v)
    return out


def normalize_index_path(path: str) -> str:
    p = path.strip()
    return p if p.startswith("/") else "/" + p


@dataclass(frozen=True)
class ListTarget:
    """One list/archive page used to discover article URLs."""

    site_base: str
    index_path: str


def list_targets_from_environ() -> tuple[ListTarget, ...]:
    """
    Build discovery targets from JSON override or index path variables.
    """
    default_base = os.environ.get(
        "BLOG_SITE_BASE", "https://www.yidaiyilu.gov.cn"
    ).rstrip("/")
    js = os.environ.get("BLOG_SCRAPER_TARGETS_JSON", "").strip()
    if js:
        data = json.loads(js)
        if not isinstance(data, list) or not data:
            raise ValueError(
                "BLOG_SCRAPER_TARGETS_JSON must be a non-empty JSON array."
            )
        targets: list[ListTarget] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise ValueError(
                    f"BLOG_SCRAPER_TARGETS_JSON[{i}] must be an object."
                )
            sb = item.get("site_base")
            ip = item.get("index_path")
            if sb is None or ip is None:
                raise ValueError(
                    f"BLOG_SCRAPER_TARGETS_JSON[{i}] requires site_base and index_path."
                )
            targets.append(
                ListTarget(
                    site_base=str(sb).rstrip("/"),
                    index_path=normalize_index_path(
                        str(ip))))
        return tuple(targets)

    primary = normalize_index_path(os.environ.get("BLOG_INDEX_PATH", "/list/w/xmzb"))
    extra = _parse_csv_urls(os.environ.get("BLOG_INDEX_PATHS", ""))
    paths_seen: set[str] = set()
    ordered: list[str] = []
    for p in (primary,) + tuple(normalize_index_path(x) for x in extra):
        if p not in paths_seen:
            paths_seen.add(p)
            ordered.append(p)
    return tuple(ListTarget(default_base, p) for p in ordered)


@dataclass(frozen=True)
class BlogScraperConfig:
    """site_base/index_path mirror the first list target (backward compatible)."""

    site_base: str
    index_path: str
    list_targets: tuple[ListTarget, ...]
    blob_connection_string: str
    blob_container_name: str
    user_agent: str
    extra_headers: dict[str, str] = field(default_factory=dict)
    content_selectors: tuple[str, ...] = (
        ".news-news-box",
        ".news-details-content",
    )
    exclude_paths: tuple[str, ...] = ("/p/178715.html",)
    translator_endpoint: str = ""
    translator_key: str = ""
    translator_region: str = ""
    scrape_timeout_seconds: float = 60.0

    @staticmethod
    def from_environ() -> BlogScraperConfig:
        conn = os.environ.get(
            "BLOG_SCRAPER_STORAGE",
            os.environ.get("AzureWebJobsStorage", ""),
        )
        container = os.environ.get("BLOB_CONTAINER_NAME", "blog-scraper")
        ua = os.environ.get(
            "HTTP_USER_AGENT",
            DEFAULT_HTTP_USER_AGENT,
        )
        raw_headers = os.environ.get("HTTP_EXTRA_HEADERS_JSON", "{}")
        selectors = _parse_csv_urls(
            os.environ.get(
                "CONTENT_SELECTORS",
                ".news-news-box,.news-details-content",
            )
        )
        excludes = _parse_csv_urls(
            os.environ.get(
                "BLOG_HTML_EXCLUDE_PATHS",
                "/p/178715.html"))
        targets = list_targets_from_environ()
        first = targets[0]

        return BlogScraperConfig(
            site_base=first.site_base,
            index_path=first.index_path,
            list_targets=targets,
            blob_connection_string=conn,
            blob_container_name=container,
            user_agent=ua,
            extra_headers=_parse_headers_json(raw_headers),
            content_selectors=selectors if selectors else (
                ".news-details-content",
            ),
            exclude_paths=excludes,
            translator_endpoint=os.environ.get(
                "TRANSLATOR_ENDPOINT",
                ""),
            translator_key=os.environ.get(
                "TRANSLATOR_KEY",
                ""),
            translator_region=os.environ.get(
                "TRANSLATOR_REGION",
                ""),
            scrape_timeout_seconds=float(
                os.environ.get("SCRAPE_TIMEOUT_SECONDS", "60")
            ),
        )


def merge_request_headers(cfg: BlogScraperConfig) -> dict[str, str]:
    headers: dict[str, str] = {
        "User-Agent": cfg.user_agent,
        "Accept": DEFAULT_ACCEPT,
        "Accept-Language": DEFAULT_ACCEPT_LANGUAGE,
        "Referer": DEFAULT_REFERER,
    }
    headers.update(cfg.extra_headers)
    return headers
