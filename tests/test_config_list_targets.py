"""List-target configuration — no HTTP."""

from __future__ import annotations

import pytest

from blog_scraper.config import ListTarget, list_targets_from_environ


def test_default_single_target(monkeypatch) -> None:
    monkeypatch.setenv("BLOG_SITE_BASE", "https://a.example")
    monkeypatch.delenv("BLOG_INDEX_PATHS", raising=False)
    monkeypatch.delenv("BLOG_SCRAPER_TARGETS_JSON", raising=False)
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/a")
    t = list_targets_from_environ()
    assert t == (ListTarget("https://a.example", "/list/a"),)


def test_extra_paths_same_site(monkeypatch) -> None:
    monkeypatch.setenv("BLOG_SITE_BASE", "https://one.example")
    monkeypatch.delenv("BLOG_SCRAPER_TARGETS_JSON", raising=False)
    monkeypatch.setenv("BLOG_INDEX_PATH", "/list/a")
    monkeypatch.setenv("BLOG_INDEX_PATHS", "/list/b,/list/a ,/list/c")
    t = list_targets_from_environ()
    assert len(t) == 3
    assert t[0] == ListTarget("https://one.example", "/list/a")
    assert ListTarget("https://one.example", "/list/b") in t


def test_json_targets_multi_site(monkeypatch) -> None:
    monkeypatch.delenv("BLOG_INDEX_PATHS", raising=False)
    monkeypatch.setenv(
        "BLOG_SCRAPER_TARGETS_JSON",
        '[{"site_base":"https://a.com","index_path":"/x"},'
        '{"site_base":"https://b.com","index_path":"/y"}]',
    )
    t = list_targets_from_environ()
    assert t == (
        ListTarget("https://a.com", "/x"),
        ListTarget("https://b.com", "/y"),
    )


def test_json_targets_empty_rejected(monkeypatch) -> None:
    monkeypatch.setenv("BLOG_SCRAPER_TARGETS_JSON", "[]")
    with pytest.raises(ValueError, match="non-empty"):
        list_targets_from_environ()
