"""CLI / container entrypoint: runs the scrape pipeline using process environment."""

from __future__ import annotations

import json
import logging
import os
import sys

from blog_scraper.config import BlogScraperConfig
from blog_scraper.pipeline import (
    PipelineOptions,
    PipelineResult,
    pipeline_options_from_dict,
    pipeline_result_summary,
    run_pipeline,
)

_LOGGER = logging.getLogger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in _TRUTHY


def _pipeline_options_from_env() -> PipelineOptions:
    """
    Prefer PIPELINE_OPTIONS_JSON when valid, otherwise SCRAPER_PIPELINE_*.

    Commas in JSON can break ``az container create`` env parsing.
    """
    raw = os.environ.get("PIPELINE_OPTIONS_JSON", "").strip()
    if raw:
        try:
            data = json.loads(raw)
            return pipeline_options_from_dict(data if isinstance(data, dict) else None)
        except json.JSONDecodeError as exc:
            _LOGGER.warning(
                "Invalid PIPELINE_OPTIONS_JSON (%s); "
                "using SCRAPER_PIPELINE_* scalars.",
                exc,
            )

    mode = os.environ.get(
        "SCRAPER_PIPELINE_MODE",
        "incremental").strip() or "incremental"
    dry = _truthy(os.environ.get("SCRAPER_PIPELINE_DRY_RUN", ""))
    force = _truthy(os.environ.get("SCRAPER_PIPELINE_FORCE", ""))
    mposts = os.environ.get("SCRAPER_PIPELINE_MAX_POSTS", "").strip()
    mpages = os.environ.get("SCRAPER_PIPELINE_MAX_PAGES", "").strip()
    max_posts = int(mposts) if mposts.isdigit() else None
    max_pages = int(mpages) if mpages.isdigit() else None
    return PipelineOptions(
        mode=mode,
        max_pages=max_pages,
        max_posts=max_posts,
        dry_run=dry,
        force=force,
    )


def _nonzero_exit(
        res: PipelineResult,
        cfg: BlogScraperConfig,
        options: PipelineOptions) -> bool:
    if any(e.startswith("discovery:") for e in res.errors):
        return True
    if not options.dry_run and not (cfg.blob_connection_string or "").strip():
        return True
    if res.errors:
        msg0 = res.errors[0]
        if msg0.startswith("BLOG_SCRAPER_STORAGE"):
            return True
    if os.environ.get("ACI_EXIT_NONZERO_ON_ERRORS", "").lower() in ("1", "true", "yes"):
        return len(res.errors) > 0
    return False


def main() -> int:
    log_level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)
    logging.basicConfig(level=log_level, format="%(levelname)s %(name)s %(message)s")

    cfg = BlogScraperConfig.from_environ()
    options = _pipeline_options_from_env()
    res = run_pipeline(cfg, options)

    summary = {
        **pipeline_result_summary(res),
        "errors": res.errors[:100],
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if _nonzero_exit(res, cfg, options) else 0


if __name__ == "__main__":
    raise SystemExit(main())
