from __future__ import annotations

from datetime import UTC, datetime

from blog_scraper.downloader import (
    _date_token,
    _post_id_from_metadata_blob,
    list_recent_posts,
)


class _Blob:
    def __init__(self, name: str, ts: datetime) -> None:
        self.name = name
        self.last_modified = ts


class _ContainerClient:
    def __init__(self, blobs: list[_Blob]) -> None:
        self._blobs = blobs

    def list_blobs(self, name_starts_with: str):
        assert name_starts_with == "posts/"
        return self._blobs


class _Service:
    def __init__(self, blobs: list[_Blob]) -> None:
        self._cc = _ContainerClient(blobs)

    def get_container_client(self, _container: str) -> _ContainerClient:
        return self._cc


def test_post_id_from_metadata_blob() -> None:
    assert _post_id_from_metadata_blob("posts/ABC123/metadata.json") == "ABC123"
    assert _post_id_from_metadata_blob("posts/ABC123/content_en.html") is None
    assert _post_id_from_metadata_blob("x/ABC123/metadata.json") is None


def test_list_recent_posts_sorted_and_limited(monkeypatch) -> None:
    blobs = [
        _Blob("posts/A/metadata.json", datetime(2026, 1, 2, tzinfo=UTC)),
        _Blob("posts/B/metadata.json", datetime(2026, 1, 3, tzinfo=UTC)),
        _Blob("posts/B/content_en.html", datetime(2026, 1, 3, tzinfo=UTC)),
        _Blob("posts/C/metadata.json", datetime(2026, 1, 1, tzinfo=UTC)),
    ]
    monkeypatch.setattr("blog_scraper.downloader._service", lambda _cs: _Service(blobs))

    rows = list_recent_posts("UseDevelopmentStorage=true", "blog-scraper", limit=2)
    assert [r.post_id for r in rows] == ["B", "A"]


def test_date_token_prefers_published_date() -> None:
    assert _date_token(
        {
            "published_date": "2026-05-08",
            "fetched_at_utc": "2026-05-09T00:00:00+00:00",
        }
    ) == "2026-05-08"
    assert _date_token(
        {
            "published_date": "",
            "fetched_at_utc": "2026-05-09T00:00:00+00:00",
        }
    ) == "2026-05-09"
