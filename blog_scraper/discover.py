from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup


_POST_HREF_RE = re.compile(r"^/p/[0-9A-Za-z_-]+\.html$")
_TOTAL_PAGES_RE = re.compile(r"共\s*(\d+)\s*页")


def post_id_from_article_url(full_url: str) -> str:
    path = urlparse(full_url).path
    stem = path.rstrip("/").split("/")[-1]
    return stem.removesuffix(".html")


def list_page_url(site_base: str, index_path: str, page: int | None) -> str:
    """Build list URL with optional ``page`` query (1-based)."""
    path_prefix = index_path if index_path.startswith("/") else "/" + index_path
    root = site_base.rstrip("/") + path_prefix
    parsed = urlparse(root)
    pairs = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k != "page"]
    if page is not None and page > 1:
        pairs.append(("page", str(int(page))))
    query = urlencode(pairs)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment))


def infer_max_page_from_html(html: str) -> int | None:
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
    m = _TOTAL_PAGES_RE.search(text)
    if m:
        return int(m.group(1))
    soup = BeautifulSoup(html, "html.parser")
    max_p = 1
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("?"):
            continue
        q = parse_qsl(href.lstrip("?"))
        for key, val in q:
            if key == "page":
                try:
                    max_p = max(max_p, int(val))
                except ValueError:
                    continue
    return max_p if max_p > 1 else None


def extract_article_hrefs(html: str, site_base: str, exclude_paths: frozenset[str]) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[str] = []
    seen: set[str] = set()
    base = site_base.rstrip("/")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not _POST_HREF_RE.match(href):
            continue
        if href in exclude_paths:
            continue
        full = base + href
        if full not in seen:
            seen.add(full)
            out.append(full)
    return out


def plan_list_pages(site_base: str, index_path: str, first_page_html: str, max_pages_cap: int | None) -> list[int]:
    """
    Return sorted 1-based page indices to crawl (always includes page 1).
    """
    inferred = infer_max_page_from_html(first_page_html) or 1
    hi = inferred
    if max_pages_cap is not None:
        hi = min(hi, max_pages_cap)
    return list(range(1, hi + 1))

