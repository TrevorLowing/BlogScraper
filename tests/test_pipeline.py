"""Pipeline tests — network-free."""

from unittest.mock import MagicMock

import pytest

from blog_scraper.config import BlogScraperConfig
from blog_scraper.pipeline import (
    PipelineOptions,
    pipeline_options_from_dict,
    pipeline_result_summary,
    run_pipeline,
)

_LIST = (
    "<html><body>"
    '<a href="/p/PIP001.html"></a>'
    "<span>共 1 页</span>"
    "</body></html>"
)
_ARTICLE = (
    "<html><body>"
    '<div class="news-details-content"><span>Chinese line one</span></div>'
    "</body></html>"
)


@pytest.fixture(name="faker_fetch")
def _faker(monkeypatch):
    def fake_fetch(url: str, headers: dict[str, str], timeout_seconds: float) -> str:
        if "/p/" in url and url.endswith(".html"):
            return _ARTICLE
        return _LIST

    monkeypatch.setattr("blog_scraper.pipeline.fetch.fetch_html", fake_fetch)


@pytest.mark.usefixtures("faker_fetch")
def test_run_pipeline_rejects_persistent_run_without_conn(monkeypatch):
    monkeypatch.delenv("AzureWebJobsStorage", raising=False)
    monkeypatch.delenv("BLOG_SCRAPER_STORAGE", raising=False)

    monkeypatch.setenv("BLOG_SITE_BASE", "https://www.example.com")
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/w/xmzb")
    monkeypatch.setenv("BLOB_CONTAINER_NAME", "c")

    cfg = BlogScraperConfig.from_environ()
    res_non = run_pipeline(cfg, PipelineOptions(dry_run=False))
    assert res_non.errors


@pytest.mark.usefixtures("faker_fetch")
def test_run_pipeline_dry_run_with_stub_upload(monkeypatch):
    monkeypatch.delenv("AzureWebJobsStorage", raising=False)
    monkeypatch.delenv("BLOG_SCRAPER_STORAGE", raising=False)
    monkeypatch.setenv("BLOG_SITE_BASE", "https://www.example.com")
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/w/xmzb")
    monkeypatch.setenv("BLOB_CONTAINER_NAME", "blob")

    mocked_upload = MagicMock()
    monkeypatch.setattr("blog_scraper.pipeline.upload_post_artifacts", mocked_upload)

    cfg = BlogScraperConfig.from_environ()
    opts = PipelineOptions(mode="historical", max_pages=1, dry_run=True, force=True)

    res = run_pipeline(cfg, opts)

    mocked_upload.assert_called_once()
    assert mocked_upload.call_args.kwargs["dry_run"] is True
    assert pipeline_result_summary(res)["posts_processed"] == 1
    assert pipeline_result_summary(res)["posts_discovered"] == 1
    assert pipeline_result_summary(res)["list_targets_attempted"] == 1


@pytest.mark.usefixtures("faker_fetch")
def test_run_pipeline_invokes_upload_when_storage_configured(monkeypatch):
    monkeypatch.setenv(
        "BLOG_SCRAPER_STORAGE",
        "DefaultEndpointsProtocol=https;AccountName=fake;"
        'AccountKey="fake";EndpointSuffix="core.windows.net"',
    )
    monkeypatch.setenv("BLOB_CONTAINER_NAME", "blog")
    monkeypatch.setenv("BLOG_SITE_BASE", "https://www.example.com")
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/w/xmzb")

    cfg = BlogScraperConfig.from_environ()
    uploads: list[dict] = []

    def capture_upload(
        _cs: str,
        _container: str,
        *,
        post_id: str,
        raw_html: str,
        zh_fragment: str,
        en_translation: str,
        metadata: object,
        dry_run: bool,
    ) -> None:
        uploads.append(
            {
                "post_id": post_id,
                "zh_fragment": zh_fragment,
                "dry_run": dry_run,
                "translator": getattr(metadata, "translator_mode"),
            },
        )

    monkeypatch.setattr("blog_scraper.pipeline.upload_post_artifacts", capture_upload)
    monkeypatch.setattr(
        "blog_scraper.pipeline.list_existing_post_ids",
        lambda *a,
        **kw: set())

    res = run_pipeline(
        cfg,
        PipelineOptions(
            mode="historical",
            max_pages=1,
            max_posts=1,
            dry_run=False,
            force=True),
    )

    assert res.posts_processed == 1
    assert len(uploads) == 1
    assert uploads[0]["post_id"] == "PIP001"
    assert uploads[0]["dry_run"] is False
    assert "Chinese line one" in uploads[0]["zh_fragment"]
    assert "<!doctype html>" in uploads[0]["zh_fragment"].lower()
    assert "<img" not in uploads[0]["zh_fragment"].lower()


_LIST_B = (
    "<html><body>"
    '<a href="/p/PIP002.html"></a>'
    "<span>共 1 页</span>"
    "</body></html>"
)


def test_two_index_paths_merge_discovered_urls(monkeypatch):
    monkeypatch.delenv("AzureWebJobsStorage", raising=False)
    monkeypatch.delenv("BLOG_SCRAPER_STORAGE", raising=False)
    monkeypatch.setenv("BLOG_SITE_BASE", "https://www.example.com")
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/a")
    monkeypatch.setenv("BLOG_INDEX_PATHS", "/list/b")
    monkeypatch.delenv("BLOG_SCRAPER_TARGETS_JSON", raising=False)

    def fake_fetch(url: str, headers: dict[str, str], timeout_seconds: float) -> str:
        if "/p/" in url and url.endswith(".html"):
            return _ARTICLE
        if "/list/b" in url.split("?", 1)[0]:
            return _LIST_B
        return _LIST

    monkeypatch.setattr("blog_scraper.pipeline.fetch.fetch_html", fake_fetch)
    mocked_upload = MagicMock()
    monkeypatch.setattr("blog_scraper.pipeline.upload_post_artifacts", mocked_upload)

    cfg = BlogScraperConfig.from_environ()
    assert len(cfg.list_targets) == 2
    opts = PipelineOptions(mode="historical", max_pages=1, dry_run=True, force=True)
    res = run_pipeline(cfg, opts)

    assert pipeline_result_summary(res)["list_targets_attempted"] == 2
    assert res.posts_discovered == 2
    assert mocked_upload.call_count == 2
    post_ids = {c.kwargs["post_id"] for c in mocked_upload.call_args_list}
    assert post_ids == {"PIP001", "PIP002"}
    from blog_scraper.pipeline import pipeline_options_to_dict

    incoming = {
        "mode": "historical",
        "max_pages": 3,
        "max_posts": None,
        "dry_run": False,
        "force": False}
    o = pipeline_options_from_dict(incoming)
    assert pipeline_options_to_dict(o) == {
        "mode": "historical",
        "max_pages": 3,
        "max_posts": None,
        "dry_run": False,
        "force": False,
    }


@pytest.mark.usefixtures("faker_fetch")
def test_run_pipeline_persists_metadata_when_translation_fails(monkeypatch):
    monkeypatch.setenv("BLOG_SCRAPER_STORAGE", "UseDevelopmentStorage=true")
    monkeypatch.setenv("BLOB_CONTAINER_NAME", "blog")
    monkeypatch.setenv("BLOG_SITE_BASE", "https://www.example.com")
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/w/xmzb")

    uploads: list[dict] = []

    def capture_upload(
        _cs: str,
        _container: str,
        *,
        post_id: str,
        raw_html: str,
        zh_fragment: str,
        en_translation: str,
        metadata: object,
        dry_run: bool,
    ) -> None:
        uploads.append(
            {
                "post_id": post_id,
                "en_translation": en_translation,
                "translator_mode": getattr(metadata, "translator_mode"),
            },
        )

    monkeypatch.setattr("blog_scraper.pipeline.upload_post_artifacts", capture_upload)
    monkeypatch.setattr(
        "blog_scraper.pipeline.list_existing_post_ids",
        lambda *a,
        **kw: set())
    monkeypatch.setattr(
        "blog_scraper.pipeline.translate.translate_zh_fragment_to_en",
        lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("translator throttled")),
    )

    cfg = BlogScraperConfig.from_environ()
    res = run_pipeline(
        cfg,
        PipelineOptions(
            mode="historical",
            max_pages=1,
            max_posts=1,
            dry_run=False,
            force=True),
    )

    assert res.posts_processed == 1
    assert len(uploads) == 1
    assert uploads[0]["post_id"] == "PIP001"
    assert uploads[0]["translator_mode"].endswith("_failed")
    assert "[TRANSLATION_FAILED]" in uploads[0]["en_translation"]
    assert any("translation_failed" in e for e in res.errors)


def test_pipeline_options_reject_invalid_mode() -> None:
    with pytest.raises(ValueError, match="mode must be one of"):
        pipeline_options_from_dict({"mode": "fullcrawl"})


def test_pipeline_options_reject_out_of_range_limits() -> None:
    with pytest.raises(ValueError, match="max_pages must be between"):
        pipeline_options_from_dict({"mode": "historical", "max_pages": 999})
    with pytest.raises(ValueError, match="max_posts must be between"):
        pipeline_options_from_dict({"mode": "historical", "max_posts": 0})
