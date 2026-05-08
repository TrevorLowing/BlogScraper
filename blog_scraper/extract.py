from __future__ import annotations

import re

from bs4 import BeautifulSoup

_DATE_RE = re.compile(r"(?P<y>\d{4})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})")


def extract_main_inner_html(html: str, selectors: tuple[str, ...]) -> tuple[str | None, str | None]:
    """
    Walk selector list; return ``(matched_selector_used, inner_html_fragment)``.
    Uses BeautifulSoup ``select_one`` (CSS selectors).
    """
    soup = BeautifulSoup(html, "html.parser")
    for sel in selectors:
        sel = sel.strip()
        if not sel:
            continue
        node = soup.select_one(sel)
        if not node:
            continue
        return sel, node.decode_contents()
    return None, None


def extract_published_date(html: str) -> str | None:
    """
    Best-effort publish date extraction as ``YYYY-MM-DD``.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Common metadata fields used by CMS templates.
    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"name": "publishdate"},
        {"name": "pubdate"},
        {"name": "date"},
    ):
        node = soup.find("meta", attrs=attrs)
        if node and node.get("content"):
            m = _DATE_RE.search(str(node.get("content")))
            if m:
                return f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"

    # Fallback: scan body text for a likely date.
    text = soup.get_text(" ", strip=True)
    m = _DATE_RE.search(text)
    if not m:
        return None
    return f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"
