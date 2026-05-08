from __future__ import annotations

import function_app


class _Timer:
    def __init__(self, past_due: bool = False):
        self.past_due = past_due


def test_scheduled_scraper_runs_in_process_when_aci_disabled(monkeypatch):
    monkeypatch.setenv("ACI_SCHEDULED", "false")

    cfg_obj = object()
    monkeypatch.setattr("function_app.BlogScraperConfig.from_environ", lambda: cfg_obj)

    seen: dict[str, object] = {}

    def fake_run_pipeline(cfg, options):
        seen["cfg"] = cfg
        seen["mode"] = options.mode
        return type("Res",
                    (),
                    {"crawl_run_id": "x",
                     "list_targets_attempted": 1,
                     "list_pages_walked": 1,
                     "posts_discovered": 1,
                     "posts_skipped_existing": 0,
                     "posts_processed": 1,
                     "errors": []})()

    monkeypatch.setattr("function_app.run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(
        "function_app.pipeline_result_summary",
        lambda _res: {
            "ok": True})

    function_app.scheduled_scraper(_Timer())

    assert seen["cfg"] is cfg_obj
    assert seen["mode"] == "incremental"


def test_scheduled_scraper_dispatches_aci_when_enabled(monkeypatch):
    monkeypatch.setenv("ACI_SCHEDULED", "true")

    monkeypatch.setattr(
        "blog_scraper.aci_invoke.aci_dispatcher_configured",
        lambda: True)
    seen: dict[str, object] = {}

    def fake_start(options, wait=False):
        seen["mode"] = options.mode
        seen["wait"] = wait
        return {"ok": True}

    monkeypatch.setattr("blog_scraper.aci_invoke.start_blog_scraper_aci", fake_start)

    function_app.scheduled_scraper(_Timer())

    assert seen == {"mode": "incremental", "wait": False}


def test_scheduled_scraper_skips_aci_when_not_configured(monkeypatch):
    monkeypatch.setenv("ACI_SCHEDULED", "true")
    monkeypatch.setattr(
        "blog_scraper.aci_invoke.aci_dispatcher_configured",
        lambda: False)

    called = {"start": False}

    def fake_start(*_args, **_kwargs):
        called["start"] = True
        return {}

    monkeypatch.setattr("blog_scraper.aci_invoke.start_blog_scraper_aci", fake_start)

    function_app.scheduled_scraper(_Timer())

    assert called["start"] is False
