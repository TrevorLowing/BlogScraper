from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass

from blog_scraper import discover, extract, fetch, translate
from blog_scraper.config import BlogScraperConfig, merge_request_headers
from blog_scraper.storage import (
    PostMetadata,
    list_existing_post_ids,
    upload_post_artifacts,
    utc_now_iso,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineOptions:
    """
    User-controlled knobs for a pipeline run.

    Plain-English intent:
    - incremental mode: check only first list page (fast, "new posts" behavior)
    - historical mode: walk more list pages for backfill
    - dry_run: execute logic but skip blob writes
    - force: reprocess posts even if they already exist in storage
    """
    mode: str = "incremental"  # incremental | historical
    # list depth cap for historical / backfill (None = all inferred)
    max_pages: int | None = None
    max_posts: int | None = None
    dry_run: bool = False
    force: bool = False


def pipeline_options_from_dict(data: dict | None) -> PipelineOptions:
    """
    Parse run options from JSON.

    Used by both:
    - HTTP request body (`/api/scrape`, `/api/scrape-aci`)
    - ACI env payload (`PIPELINE_OPTIONS_JSON`)
    """
    if not data or not isinstance(data, dict):
        return PipelineOptions()
    mode = data.get("mode", "incremental")
    max_pages = data.get("max_pages")
    max_posts = data.get("max_posts")
    return PipelineOptions(
        mode=str(mode),
        max_pages=int(max_pages) if max_pages is not None else None,
        max_posts=int(max_posts) if max_posts is not None else None,
        dry_run=bool(data.get("dry_run", False)),
        force=bool(data.get("force", False)),
    )


def pipeline_options_to_dict(options: PipelineOptions) -> dict:
    return {
        "mode": options.mode,
        "max_pages": options.max_pages,
        "max_posts": options.max_posts,
        "dry_run": options.dry_run,
        "force": options.force,
    }


@dataclass
class PipelineResult:
    crawl_run_id: str
    list_pages_walked: int
    posts_discovered: int
    posts_skipped_existing: int
    posts_processed: int
    errors: list[str]
    list_targets_attempted: int = 0


def _discover_urls_for_one_index(
    *,
    site_base: str,
    index_path: str,
    headers: dict[str, str],
    scrape_timeout_seconds: float,
    options: PipelineOptions,
    exclude_paths: frozenset[str],
) -> tuple[list[str], int]:
    first_url = discover.list_page_url(site_base, index_path, None)
    first_html = fetch.fetch_html(
        first_url,
        headers=headers,
        timeout_seconds=scrape_timeout_seconds)

    incremental_cap = 1 if options.mode == "incremental" else options.max_pages
    pages = discover.plan_list_pages(site_base, index_path, first_html, incremental_cap)

    urls: list[str] = []
    seen: set[str] = set()
    excl = exclude_paths

    for pg in pages:
        u = discover.list_page_url(site_base, index_path, pg if pg > 1 else None)
        html = first_html if pg == 1 else fetch.fetch_html(
            u, headers=headers, timeout_seconds=scrape_timeout_seconds)
        for href in discover.extract_article_hrefs(html, site_base, excl):
            if href not in seen:
                seen.add(href)
                urls.append(href)

    return urls, len(pages)


def discover_all_urls(
    cfg: BlogScraperConfig,
    headers: dict[str, str],
    options: PipelineOptions,
) -> tuple[list[str], int, list[str]]:
    """
    Discover unique article URLs across all configured list targets.

    Returns:
    - deduplicated article URLs
    - total list pages walked
    - non-fatal discovery errors (per target)
    """
    excl = frozenset(cfg.exclude_paths)
    out: list[str] = []
    global_seen: set[str] = set()
    pages_walked = 0
    disc_errs: list[str] = []

    for target in cfg.list_targets:
        tag = f"{target.site_base}{target.index_path}"
        try:
            part, walked = _discover_urls_for_one_index(
                site_base=target.site_base,
                index_path=target.index_path,
                headers=headers,
                scrape_timeout_seconds=cfg.scrape_timeout_seconds,
                options=options,
                exclude_paths=excl,
            )
            pages_walked += walked
            for u in part:
                if u not in global_seen:
                    global_seen.add(u)
                    out.append(u)
        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("Discovery failed for %s", tag)
            disc_errs.append(f"discovery[{tag}]: {exc}")

    return out, pages_walked, disc_errs


def run_pipeline(cfg: BlogScraperConfig, options: PipelineOptions) -> PipelineResult:
    """
    End-to-end scrape pipeline.

    Flow:
    1) validate required config
    2) discover article URLs
    3) skip existing posts unless force=true
    4) fetch + extract + translate per post
    5) persist artifacts + metadata to blob
    6) return summary counters + collected errors
    """
    crawl_run_id = str(uuid.uuid4())
    headers = merge_request_headers(cfg)
    _LOGGER.info(
        "Pipeline start run_id=%s mode=%s dry_run=%s force=%s max_pages=%s "
        "max_posts=%s targets=%s",
        crawl_run_id,
        options.mode,
        options.dry_run,
        options.force,
        options.max_pages,
        options.max_posts,
        len(cfg.list_targets),
    )

    result = PipelineResult(
        crawl_run_id=crawl_run_id,
        list_pages_walked=0,
        posts_discovered=0,
        posts_skipped_existing=0,
        posts_processed=0,
        errors=[],
        list_targets_attempted=len(cfg.list_targets),
    )

    # Real writes require a blob connection string.
    # We allow missing storage only in dry-run mode for local testing/debugging.
    if not cfg.blob_connection_string and not options.dry_run:
        result.errors.append(
            "BLOG_SCRAPER_STORAGE (or AzureWebJobsStorage) is empty - "
            "cannot persist without dry_run."
        )
        return result

    try:
        urls, walked, discovery_errors = discover_all_urls(cfg, headers, options)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.exception("Discovery phase failed")
        result.errors.append(f"discovery: {exc}")
        return result

    result.errors.extend(discovery_errors)
    result.list_pages_walked = walked
    result.posts_discovered = len(urls)
    _LOGGER.info(
        "Discovery complete run_id=%s pages_walked=%s posts_discovered=%s "
        "discovery_errors=%s",
        crawl_run_id,
        result.list_pages_walked,
        result.posts_discovered,
        len(discovery_errors),
    )

    # Snapshot existing post ids once to avoid repeated blob lookups for each post.
    existing: set[str] = set()
    if cfg.blob_connection_string and not options.force:
        existing = list_existing_post_ids(
            cfg.blob_connection_string,
            cfg.blob_container_name)

    # Translator mode is recorded in metadata for observability and auditing.
    translator_mode = "stub" if not cfg.translator_key.strip() else "azure_translator"

    for url in urls:
        if (
            options.max_posts is not None
            and result.posts_processed >= options.max_posts
        ):
            break

        post_id = discover.post_id_from_article_url(url)

        try:
            # Skip already-seen posts unless the caller explicitly requests
            # reprocessing.
            if cfg.blob_connection_string and not options.force and post_id in existing:
                result.posts_skipped_existing += 1
                _LOGGER.info(
                    "Post skipped run_id=%s post_id=%s reason=already_exists",
                    crawl_run_id,
                    post_id,
                )
                continue

            raw_html = fetch.fetch_html(
                url, headers=headers, timeout_seconds=cfg.scrape_timeout_seconds)
            selector_used, zh_fragment = extract.extract_main_inner_html(
                raw_html, cfg.content_selectors)
            if not zh_fragment:
                msg = f"empty_main_content_selector post_id={post_id} url={url}"
                _LOGGER.warning(msg)
                result.errors.append(msg)
                continue

            zh_hash_source = zh_fragment.encode("utf-8")
            content_sha = hashlib.sha256(zh_hash_source).hexdigest()
            published_date = extract.extract_published_date(raw_html)
            translator_mode_for_post = translator_mode

            try:
                en_text = translate.translate_zh_fragment_to_en(zh_fragment, cfg)
            except Exception as exc:  # noqa: BLE001
                # Preserve scraped content and metadata even when translator
                # throttles/fails.
                _LOGGER.warning(
                    "Translation failed for post_id=%s; persisting zh content only: %s",
                    post_id,
                    exc)
                result.errors.append(f"{url}: translation_failed: {exc}")
                en_text = "[TRANSLATION_FAILED]\n" + zh_fragment
                translator_mode_for_post = f"{translator_mode}_failed"

            md = PostMetadata(
                canonical_url=url,
                post_id=post_id,
                published_date=published_date,
                fetched_at_utc=utc_now_iso(),
                content_sha256=content_sha,
                source_language="zh-Hans",
                content_selector_used=selector_used,
                translator_mode=translator_mode_for_post,
                crawl_run_id=crawl_run_id,
            )

            upload_post_artifacts(
                cfg.blob_connection_string,
                cfg.blob_container_name,
                post_id=post_id,
                raw_html=raw_html,
                zh_fragment=zh_fragment,
                en_translation=en_text,
                metadata=md,
                dry_run=options.dry_run,
            )

            # Keep in-memory dedupe set consistent with successful writes.
            existing.add(post_id)
            result.posts_processed += 1
            _LOGGER.info(
                "Post processed run_id=%s post_id=%s selector=%s translator_mode=%s",
                crawl_run_id,
                post_id,
                selector_used,
                translator_mode_for_post,
            )

        except Exception as exc:  # noqa: BLE001
            _LOGGER.exception("Post failed url=%s", url)
            result.errors.append(f"{url}: {exc}")

    _LOGGER.info(
        "Pipeline end run_id=%s discovered=%s skipped=%s processed=%s errors=%s",
        crawl_run_id,
        result.posts_discovered,
        result.posts_skipped_existing,
        result.posts_processed,
        len(result.errors),
    )
    return result


def pipeline_result_summary(res: PipelineResult) -> dict:
    return {
        "crawl_run_id": res.crawl_run_id,
        "list_targets_attempted": res.list_targets_attempted,
        "list_pages_walked": res.list_pages_walked,
        "posts_discovered": res.posts_discovered,
        "posts_skipped_existing": res.posts_skipped_existing,
        "posts_processed": res.posts_processed,
        "error_count": len(res.errors),
    }
