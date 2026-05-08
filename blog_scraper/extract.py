from __future__ import annotations

import re

from bs4 import BeautifulSoup

_DATE_RE = re.compile(r"(?P<y>\d{4})[./-](?P<m>\d{1,2})[./-](?P<d>\d{1,2})")


def extract_main_inner_html(
    html: str, selectors: tuple[str, ...]
) -> tuple[str | None, str | None]:
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
                year = int(m.group("y"))
                month = int(m.group("m"))
                day = int(m.group("d"))
                return f"{year:04d}-{month:02d}-{day:02d}"

    # Fallback: scan body text for a likely date.
    text = soup.get_text(" ", strip=True)
    m = _DATE_RE.search(text)
    if not m:
        return None
    return f"{int(m.group('y')):04d}-{int(m.group('m')):02d}-{int(m.group('d')):02d}"


def sanitize_fragment_for_output(fragment_html: str, *, include_images: bool) -> str:
    """
    Remove external-dependency tags from output fragment.

    Images are removed by default and can be retained with include_images=True.
    """
    soup = BeautifulSoup(fragment_html or "", "html.parser")
    for tag in soup(
        ["script", "style", "link", "iframe", "object", "embed", "video", "audio"]
    ):
        tag.decompose()
    if not include_images:
        for tag in soup(["img", "picture", "source"]):
            tag.decompose()
    return soup.decode_contents()


def wrap_readable_html(fragment_html: str, *, lang: str) -> str:
    """
    Wrap fragment in a self-contained readable HTML document with basic reset.
    """
    safe_lang = (lang or "en").strip() or "en"
    return (
        "<!doctype html>"
        f'<html lang="{safe_lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<style>"
        "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}"
        "html,body{width:100%;}"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',"
        "Roboto,Arial,sans-serif;"
        "line-height:1.65;font-size:18px;color:#1f2937;background:#ffffff;"
        "padding:24px;max-width:860px;margin:0 auto;}"
        "p{margin:0 0 1rem;}"
        "h1,h2,h3,h4,h5,h6{line-height:1.3;margin:1.2rem 0 0.8rem;font-weight:700;}"
        "ul,ol{margin:0 0 1rem 1.5rem;}"
        "li{margin:0.25rem 0;}"
        "a{color:#2563eb;text-decoration:underline;word-break:break-word;}"
        "blockquote{border-left:4px solid #d1d5db;padding-left:0.9rem;"
        "color:#4b5563;margin:1rem 0;}"
        "table{border-collapse:collapse;width:100%;margin:1rem 0;}"
        "th,td{border:1px solid #d1d5db;padding:0.5rem;text-align:left;}"
        "</style></head><body>"
        f"{fragment_html}"
        "</body></html>"
    )
