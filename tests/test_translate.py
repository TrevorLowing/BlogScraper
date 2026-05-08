from __future__ import annotations

import httpx

from blog_scraper.config import BlogScraperConfig
from blog_scraper.translate import translate_zh_fragment_to_en


class _FakeClient:
    def __init__(self, responses: list[httpx.Response]):
        self._responses = responses
        self.calls = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, *args, **kwargs):
        idx = self.calls
        self.calls += 1
        return self._responses[idx]


def _cfg() -> BlogScraperConfig:
    return BlogScraperConfig(
        site_base="https://example.com",
        index_path="/list",
        list_targets=(),
        blob_connection_string="",
        blob_container_name="blog-scraper",
        user_agent="ua",
        translator_endpoint="https://api.cognitive.microsofttranslator.com",
        translator_key="key",
        translator_region="region",
    )


def _resp(
        code: int,
        payload: list[dict],
        retry_after: str | None = None) -> httpx.Response:
    req = httpx.Request(
        "POST",
        "https://api.cognitive.microsofttranslator.com/translate")
    headers = {"Retry-After": retry_after} if retry_after else {}
    return httpx.Response(code, request=req, headers=headers, json=payload)


def test_translate_retries_429_then_succeeds(monkeypatch):
    responses = [
        _resp(429, []),
        _resp(200, [{"translations": [{"text": "hello"}]}]),
    ]
    fake = _FakeClient(responses)
    monkeypatch.setattr("blog_scraper.translate.httpx.Client", lambda **_kwargs: fake)
    sleeps: list[float] = []
    monkeypatch.setattr(
        "blog_scraper.translate.time.sleep",
        lambda s: sleeps.append(
            float(s)))

    out = translate_zh_fragment_to_en("你好", _cfg())

    assert out == "hello"
    assert fake.calls == 2
    assert sleeps == [1.0]


def test_translate_honors_retry_after_header(monkeypatch):
    responses = [
        _resp(429, [], retry_after="3"),
        _resp(200, [{"translations": [{"text": "world"}]}]),
    ]
    fake = _FakeClient(responses)
    monkeypatch.setattr("blog_scraper.translate.httpx.Client", lambda **_kwargs: fake)
    sleeps: list[float] = []
    monkeypatch.setattr(
        "blog_scraper.translate.time.sleep",
        lambda s: sleeps.append(
            float(s)))

    out = translate_zh_fragment_to_en("世界", _cfg())

    assert out == "world"
    assert sleeps == [3.0]
