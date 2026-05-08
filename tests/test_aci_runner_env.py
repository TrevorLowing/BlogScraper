import json

from blog_scraper.pipeline import PipelineOptions


def test_aci_runner_scalars_when_json_invalid(monkeypatch) -> None:
    from blog_scraper.aci_runner import _pipeline_options_from_env

    monkeypatch.setenv("PIPELINE_OPTIONS_JSON", "{bad json")
    monkeypatch.setenv("SCRAPER_PIPELINE_DRY_RUN", "true")
    monkeypatch.setenv("SCRAPER_PIPELINE_MAX_POSTS", "2")
    monkeypatch.setenv("SCRAPER_PIPELINE_MODE", "historical")

    opts = _pipeline_options_from_env()
    assert opts.dry_run is True
    assert opts.max_posts == 2
    assert opts.mode == "historical"


def test_aci_runner_prefers_valid_json(monkeypatch) -> None:
    from blog_scraper.aci_runner import _pipeline_options_from_env

    monkeypatch.setenv("PIPELINE_OPTIONS_JSON", json.dumps({"mode": "incremental", "dry_run": True, "max_posts": 9}))
    monkeypatch.setenv("SCRAPER_PIPELINE_MAX_POSTS", "1")

    opts = _pipeline_options_from_env()
    assert opts.max_posts == 9
