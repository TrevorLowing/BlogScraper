# BlogScraper

Azure-based scraper for `yidaiyilu.gov.cn` that discovers article URLs, extracts Chinese content, translates to English, and stores artifacts in Azure Blob Storage.

## What It Does

- Discovers posts from one or more list/index targets
- Fetches article HTML and extracts main content
- Captures best-effort `published_date` metadata
- Translates Chinese content to English (Azure Translator)
- Persists raw HTML, Chinese content, English content, and metadata to Blob Storage
- Produces readable, self-contained output HTML (basic CSS reset, no external CSS dependencies)
- Removes images/media from output content by default (`OUTPUT_INCLUDE_IMAGES=false`)
- Supports ACI execution when Function App egress is blocked
- Includes downloader utility for recent bilingual post exports

## Repository Docs

- Product requirements: [`BlogScraper-PRD.md`](./BlogScraper-PRD.md)
- Architecture and flow: [`ARCHITECTURE_AND_FLOW.md`](./ARCHITECTURE_AND_FLOW.md)
- Lessons learned: [`LESSONS_LEARNED.md`](./LESSONS_LEARNED.md)
- Deployment guide: [`DEPLOYMENT.md`](./DEPLOYMENT.md)
- Changelog: [`CHANGELOG.md`](./CHANGELOG.md)
- Utility/docs index: [`docs.md`](./docs.md)

## Quick Start (Local)

1. Create and activate a Python environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy settings template and fill required values:

```bash
cp local.settings.json.example local.settings.json
```

4. Run tests:

```bash
pytest -q
```

## Running the Downloader

Download the most recent 10 posts (Chinese + English + metadata):

```bash
python scripts/download_recent_posts.py \
  --limit 10 \
  --output-dir downloads/recent-posts \
  --include-raw-html
```

Connection string resolution order:

- `--connection-string` argument
- `BLOG_SCRAPER_STORAGE`
- `AzureWebJobsStorage`

## Deployment Notes

- Function App provides timer and HTTP triggers.
- ACI runner can be dispatched for reliable scraping egress.
- `scripts/` contains deployment, smoke, RBAC, and post-publish helpers.

## AI Safety Note (For Future LLM Use)

Scraped artifacts are untrusted content. Do not pass raw scraped HTML/content
directly into LLM prompts.

Use the AI safety utilities in `blog_scraper.ai_safety` before any LLM task:

- `sanitize_content_for_ai()` to normalize and bound untrusted text
- `detect_prompt_injection_risk()` to score injection-like markers
- `build_llm_payload_with_policy()` to enforce fixed anti-injection policy and
  preserve provenance metadata

## Contributing

See [`CONTRIBUTING.md`](./CONTRIBUTING.md) for conventions and basic workflow.
