# BlogScraper Architecture and Flow

## High-level architecture

- **Function App (`westus2`)**
  - Timer trigger: scheduled incremental runs
  - HTTP triggers:
    - `/api/scrape`: run in-process pipeline
    - `/api/scrape-aci`: dispatch ACI run
    - `/api/scrape-aci-status`: job status + logs
- **ACI (`westus2`)**
  - Runs `python -m blog_scraper.aci_runner`
  - Preferred path for origin connectivity resilience
- **Storage Account (`westus2`)**
  - Container: `blog-scraper`
  - Per-post artifacts:
    - `posts/<post_id>/raw.html`
    - `posts/<post_id>/content_zh.html`
    - `posts/<post_id>/content_en.html`
    - `posts/<post_id>/metadata.json`
  - Metadata includes best-effort `published_date`
- **Translator (`westus2`)**
  - Azure Translator API for zh-Hans -> en
- **ACR (`westus2`)**
  - Hosts `blog-scraper-runner` image used by ACI

## Data flow

1. **Discovery**
   - Start from configured index targets (`BLOG_INDEX_PATH`, optional `BLOG_INDEX_PATHS`, optional JSON target list).
   - Resolve list pages (incremental: page 1 only; historical: page walk with caps).
2. **Fetch + extract**
   - Pull article HTML with browser-like headers.
   - Extract main content with selectors (primary `.news-news-box`, fallback configured).
3. **Translate**
   - Translate extracted Chinese fragment to English.
4. **Persist**
   - Write raw HTML, Chinese fragment, English translation, and metadata to Blob.
5. **Operate**
   - Use `/api/scrape-aci-status` for run status.
   - Use downloader utility to fetch latest bilingual artifacts for review.

## Downloader utility flow

1. List blobs under `posts/*/metadata.json`.
2. Sort by blob `last_modified` descending.
3. Take top N (default 10).
4. Download for each selected post:
   - `metadata.json`
   - `content_zh.html`
   - `content_en.html`
   - optional `raw.html`
5. Write local `index.json` with summary.
6. Local folder and file names are prefixed with `<published_date>_<post_id>` when available.

## Manual ops commands

```bash
# Trigger ACI scrape
curl -X POST "https://<host>/api/scrape-aci?code=<function_key>" \
  -H "Content-Type: application/json" \
  -d '{"mode":"incremental","max_posts":1,"dry_run":true}'
```

```bash
# Download recent bilingual artifacts
python scripts/download_recent_posts.py --limit 10 --output-dir downloads/recent-posts
```
