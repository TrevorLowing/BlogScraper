"""Azure Functions entrypoint (timer + HTTP) for BlogScraper."""

from __future__ import annotations

import json
import logging
import os

import azure.functions as func

from blog_scraper.config import BlogScraperConfig
from blog_scraper.pipeline import (
    PipelineOptions,
    pipeline_options_from_dict,
    pipeline_result_summary,
    run_pipeline,
)

_LOGGER = logging.getLogger(__name__)

app = func.FunctionApp()
_TRUTHY = {"1", "true", "yes", "on"}


def _options_from_http_body(raw: bytes | None) -> PipelineOptions:
    if not raw:
        return PipelineOptions()
    try:
        data = json.loads(raw.decode("utf-8"))
        return pipeline_options_from_dict(data if isinstance(data, dict) else None)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError):
        return PipelineOptions()


@app.timer_trigger(
    schedule=os.environ.get("SCRAPER_TIMER_SCHEDULE", "0 0 10 * * *"),
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def scheduled_scraper(timer: func.TimerRequest) -> None:
    if getattr(timer, "past_due", False):
        _LOGGER.info("Scheduled run firing (past due).")
    if os.environ.get("ACI_SCHEDULED", "").lower() in _TRUTHY:
        from blog_scraper.aci_invoke import aci_dispatcher_configured, start_blog_scraper_aci

        if not aci_dispatcher_configured():
            _LOGGER.error("ACI_SCHEDULED is set but ACI dispatcher env is incomplete; skipping run.")
            return
        try:
            info = start_blog_scraper_aci(PipelineOptions(mode="incremental"), wait=False)
            _LOGGER.info("Dispatched incremental scrape via ACI: %s", info)
        except ValueError as exc:
            _LOGGER.warning("ACI dispatcher rejected scheduled run due to invalid configuration: %s", exc)
        except RuntimeError:
            _LOGGER.exception("Scheduled ACI dispatch runtime failure.")
        return
    cfg = BlogScraperConfig.from_environ()
    res = run_pipeline(cfg, PipelineOptions(mode="incremental"))
    summary = pipeline_result_summary(res)
    _LOGGER.info("Incremental scrape summary: %s", summary)


@app.route(route="scrape", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def scrape_http(req: func.HttpRequest) -> func.HttpResponse:
    cfg = BlogScraperConfig.from_environ()
    options = _options_from_http_body(req.get_body())
    res = run_pipeline(cfg, options)
    body = {
        **pipeline_result_summary(res),
        "errors": res.errors[:50],
    }
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False),
        status_code=200,
        mimetype="application/json; charset=utf-8",
    )


@app.route(route="scrape-aci", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def scrape_aci_http(req: func.HttpRequest) -> func.HttpResponse:
    """Start a scrape in Azure Container Instances (egress differs from Consumption Functions)."""

    from blog_scraper.aci_invoke import aci_dispatcher_configured, start_blog_scraper_aci

    try:
        if not aci_dispatcher_configured():
            return func.HttpResponse(
                json.dumps(
                    {
                        "error": "aci_not_configured",
                        "hint": (
                            "Set ACI_SUBSCRIPTION_ID (or AZURE_SUBSCRIPTION_ID), ACI_RESOURCE_GROUP, "
                            "ACI_IMAGE, ACI_REGISTRY_USERNAME, and ACI_REGISTRY_PASSWORD when using "
                            "ACR images (see local.settings.json.example)."
                        ),
                    },
                ),
                status_code=400,
                mimetype="application/json; charset=utf-8",
            )

        options = _options_from_http_body(req.get_body())
        info = start_blog_scraper_aci(options, wait=False)
        return func.HttpResponse(
            json.dumps(info, ensure_ascii=False),
            status_code=202,
            mimetype="application/json; charset=utf-8",
        )
    except ValueError as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json; charset=utf-8",
        )
    except RuntimeError as exc:
        return func.HttpResponse(
            json.dumps({"error": f"aci_dispatch_failed: {exc}"}, ensure_ascii=False),
            status_code=502,
            mimetype="application/json; charset=utf-8",
        )


@app.route(route="scrape-aci-status", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def scrape_aci_status_http(req: func.HttpRequest) -> func.HttpResponse:
    """Fetch provisioning state / tail logs for a container group."""

    from blog_scraper.aci_invoke import fetch_aci_job_status

    try:
        name = req.params.get("group") or req.params.get("name")
        rg_override = req.params.get("rg")
        if not name:
            return func.HttpResponse(
                json.dumps({"error": 'Query "group=<container_group_name>" is required.'}),
                status_code=400,
                mimetype="application/json; charset=utf-8",
            )

        summary = fetch_aci_job_status(name, resource_group=rg_override.strip() if rg_override else None)
        return func.HttpResponse(
            json.dumps(summary, ensure_ascii=False),
            status_code=200,
            mimetype="application/json; charset=utf-8",
        )
    except ValueError as exc:
        return func.HttpResponse(
            json.dumps({"error": str(exc)}, ensure_ascii=False),
            status_code=400,
            mimetype="application/json; charset=utf-8",
        )
