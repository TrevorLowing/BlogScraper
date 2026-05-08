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


def _error_response(
    *,
    code: str,
    message: str,
    status_code: int,
) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps({"error": code, "message": message}, ensure_ascii=False),
        status_code=status_code,
        mimetype="application/json; charset=utf-8",
    )


def _options_from_http_body(raw: bytes | None) -> PipelineOptions:
    """
    Parse optional JSON body into PipelineOptions.

    For HTTP endpoints we fail closed on malformed input.
    """
    if not raw:
        return PipelineOptions()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("Request body must be valid JSON.") from exc
    if data is None:
        return PipelineOptions()
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")
    return pipeline_options_from_dict(data)


def _is_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in _TRUTHY


@app.timer_trigger(
    schedule=os.environ.get("SCRAPER_TIMER_SCHEDULE", "0 0 10 * * *"),
    arg_name="timer",
    run_on_startup=False,
    use_monitor=True,
)
def scheduled_scraper(timer: func.TimerRequest) -> None:
    """
    Timer-triggered incremental run.

    Behavior:
    - If ACI_SCHEDULED is truthy, dispatches a container run (preferred when
      Function egress is unreliable for the source website).
    - Otherwise runs the pipeline directly inside Function runtime.
    """
    if getattr(timer, "past_due", False):
        _LOGGER.info("Scheduled run firing (past due).")
    if os.environ.get("ACI_SCHEDULED", "").lower() in _TRUTHY:
        from blog_scraper.aci_invoke import (
            aci_dispatcher_configured,
            start_blog_scraper_aci,
        )

        if not aci_dispatcher_configured():
            _LOGGER.error(
                "ACI_SCHEDULED is set but ACI dispatcher env is incomplete; "
                "skipping run."
            )
            return
        try:
            info = start_blog_scraper_aci(
                PipelineOptions(
                    mode="incremental"),
                wait=False)
            _LOGGER.info(
                "Dispatched incremental scrape via ACI: %s",
                info,
            )
        except ValueError as exc:
            _LOGGER.warning(
                "ACI dispatcher rejected scheduled run due to invalid "
                "configuration: %s",
                exc,
            )
        except RuntimeError:
            _LOGGER.exception("Scheduled ACI dispatch runtime failure.")
        return
    cfg = BlogScraperConfig.from_environ()
    res = run_pipeline(cfg, PipelineOptions(mode="incremental"))
    summary = pipeline_result_summary(res)
    _LOGGER.info(
        "Incremental scrape summary: %s",
        summary,
    )


@app.route(route="scrape", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
def scrape_http(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP API to run scraper in-process and return a compact JSON summary."""
    cfg = BlogScraperConfig.from_environ()
    try:
        options = _options_from_http_body(req.get_body())
    except ValueError as exc:
        _LOGGER.warning("Invalid scrape request options: %s", exc)
        return _error_response(
            code="invalid_request_options",
            message="Invalid scrape request options.",
            status_code=400,
        )
    _LOGGER.info(
        "HTTP scrape start mode=%s dry_run=%s force=%s max_pages=%s max_posts=%s",
        options.mode,
        options.dry_run,
        options.force,
        options.max_pages,
        options.max_posts,
    )
    res = run_pipeline(cfg, options)
    body = {
        **pipeline_result_summary(res),
        "errors": res.errors[:50],
    }
    _LOGGER.info(
        "HTTP scrape end run_id=%s processed=%s skipped=%s errors=%s",
        body.get("crawl_run_id"),
        body.get("posts_processed"),
        body.get("posts_skipped_existing"),
        body.get("error_count"),
    )
    return func.HttpResponse(
        json.dumps(body, ensure_ascii=False),
        status_code=200,
        mimetype="application/json; charset=utf-8",
    )


@app.route(
    route="scrape-aci",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def scrape_aci_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP API to dispatch a one-shot ACI scrape job.

    Useful when you want better network resilience than in-process execution.
    Returns 202 with the job identity when dispatch succeeds.
    """

    from blog_scraper.aci_invoke import (
        aci_dispatcher_configured,
        start_blog_scraper_aci,
    )

    try:
        if not aci_dispatcher_configured():
            return _error_response(
                code="aci_not_configured",
                message=(
                    "ACI dispatcher settings are incomplete "
                    "(subscription/resource group/image and pull auth settings)."
                ),
                status_code=400,
            )

        options = _options_from_http_body(req.get_body())
        _LOGGER.info(
            "HTTP scrape-aci dispatch start mode=%s dry_run=%s force=%s "
            "max_pages=%s max_posts=%s",
            options.mode,
            options.dry_run,
            options.force,
            options.max_pages,
            options.max_posts,
        )
        info = start_blog_scraper_aci(options, wait=False)
        _LOGGER.info(
            "HTTP scrape-aci dispatch accepted container_group=%s resource_group=%s",
            info.get("container_group_name"),
            info.get("resource_group"),
        )
        return func.HttpResponse(
            json.dumps(info, ensure_ascii=False),
            status_code=202,
            mimetype="application/json; charset=utf-8",
        )
    except ValueError as exc:
        _LOGGER.warning("ACI dispatch rejected request: %s", exc)
        return _error_response(
            code="invalid_request_or_configuration",
            message="Invalid request or ACI dispatcher configuration.",
            status_code=400,
        )
    except RuntimeError as exc:
        _LOGGER.exception("ACI dispatch failed: %s", exc)
        return _error_response(
            code="aci_dispatch_failed",
            message="Failed to dispatch ACI job.",
            status_code=502,
        )


@app.route(route="scrape-aci-status",
           methods=["GET"],
           auth_level=func.AuthLevel.FUNCTION)
def scrape_aci_status_http(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP API to read state and tail logs for a previously dispatched ACI job.

    Required query param: `group=<container_group_name>`
    Optional query param: `rg=<resource_group_override>`
    """

    from blog_scraper.aci_invoke import fetch_aci_job_status

    try:
        name = req.params.get("group") or req.params.get("name")
        rg_override = req.params.get("rg")
        include_logs = _is_truthy(req.params.get("include_logs"))
        if not name:
            return _error_response(
                code="missing_group",
                message='Query "group=<container_group_name>" is required.',
                status_code=400,
            )

        summary = fetch_aci_job_status(
            name,
            resource_group=rg_override.strip() if rg_override else None,
            include_logs=include_logs,
        )
        return func.HttpResponse(
            json.dumps(summary, ensure_ascii=False),
            status_code=200,
            mimetype="application/json; charset=utf-8",
        )
    except ValueError as exc:
        _LOGGER.warning("Invalid scrape-aci-status request: %s", exc)
        return _error_response(
            code="invalid_status_request",
            message="Invalid status request parameters.",
            status_code=400,
        )
