from pathlib import Path

from blog_scraper import extract


def test_extract_prefers_news_news_box_then_details():
    fixture = Path(__file__).resolve().parent / "fixtures" / "post_min.html"
    html = fixture.read_text(encoding="utf-8")

    sel, inner = extract.extract_main_inner_html(html, (".missing", ".news-details-content"))
    assert sel == ".news-details-content"
    assert "<p>测试正文</p>" in inner


def test_extract_published_date_from_meta():
    html = (
        "<html><head>"
        '<meta property="article:published_time" content="2025-11-09 15:00:00">'
        "</head><body><div>正文</div></body></html>"
    )
    assert extract.extract_published_date(html) == "2025-11-09"
