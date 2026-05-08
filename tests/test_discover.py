from pathlib import Path

from blog_scraper import discover


def _fixture(name: str) -> str:
    return (
        Path(__file__).resolve().parent /
        "fixtures" /
        name).read_text(
        encoding="utf-8")


def test_infer_max_pages_from_cn_text():
    html = _fixture("list_min.html")
    assert discover.infer_max_page_from_html(html) == 3


def test_extract_article_hrefs_excludes_about():
    html = _fixture("list_min.html")
    hrefs = discover.extract_article_hrefs(
        html,
        "https://www.example.com",
        frozenset({"/p/178715.html"}),
    )
    assert hrefs == ["https://www.example.com/p/XYZ123ZZ.html"]


def test_post_id():
    assert discover.post_id_from_article_url("https://x.com/p/ABC12.html") == "ABC12"
