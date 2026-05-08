# Project Requirements: Secure Azure Scheduled Blog Scraper

## Overview

Develop a timer-triggered Azure Function that discovers posts from a curated blog index (**incrementally on a schedule** and via **historical full backfill** when needed), fetches **Chinese** HTML for each post, **translates the main textual content to English** from the **`news-news-box`** region, persists artifacts securely to Azure Blob Storage, and honors **maximum network isolation** to limit lateral movement. The delivery must include **automated end-to-end tests** (fixture-based CI plus optional live smoke) proving the full pipeline.

**Reference URLs**

- **Index/list page:** https://www.yidaiyilu.gov.cn/list/w/xmzb  
- **Example article:** https://www.yidaiyilu.gov.cn/p/0ODODQPQ.html  

## Key Components

1. **Compute:** Azure Function App with **timer trigger** (`TimerTrigger`; schedule via app settings / CRON).

2. **Optional triggers for operations & QA:** HTTP-triggered or queue-driven **manual / pipeline runs** must be supported so **end-to-end tests** and **historical backfills** can run outside the cron schedule — secured (APIM / function keys / Managed Identity callers / VNet-only as policy dictates).

3. **Storage:** Azure Blob Storage for blobs (recommended layout: partitioned by crawl date / post ID; see Data Model).

4. **Translation:** Azure AI Translator (or approved equivalent **managed** service under the same isolation story) — not ad-hoc unauthenticated APIs unless approved.

5. **Security / isolation:** VNet integration for the Function App, Managed Identity for storage and translation credentials, NSGs restricting egress to allowlisted destinations only.

## Requirements

### Downloader utility

- Add an operator utility that downloads the **10 most recent posts** from Azure Blob (configurable `--limit`) including:
  - Chinese extracted content (`content_zh.html`)
  - English translated content (`content_en.html`)
  - `metadata.json` for each post
- Utility should support optional raw HTML download for debugging (`raw.html`).
- Utility output should be deterministic and review-friendly:
  - Folder per post under an output directory, including published date token when available
  - `index.json` summary file listing post IDs, URLs, and local paths
- Utility must run both locally and in CI/manual jobs using existing storage settings (`BLOG_SCRAPER_STORAGE` or `AzureWebJobsStorage`).

### Automation & scheduling

- Runs on a **configurable cadence**: **daily** or **weekly** (and optionally **custom CRON**) via configuration — no redeploy needed to switch cadence.
- **Idempotent runs:** Safe to run multiple times per day without duplicating blobs; deterministic blob naming keyed by canonical post identifier and crawl version metadata.
- **Observability:** Structured logs/metrics for run start/end, posts discovered vs skipped, failures per URL, translation latency/errors.

### Crawl modes: incremental vs historical (full backfill)

- **Incremental (default for scheduled runs):** Discover links from configured index URL(s); process only posts **not yet present** in storage (or whose **content hash** changed if re-sync is configured).
- **Historical / full corpus:** A dedicated **backfill mode** (config flag or invocation payload) must **enumerate every accessible list/index page** (pagination, “load more,” or deterministic page-index URLs — **implement per site mechanics**) until no new listing pages remain, enqueue **all** article URLs discovered, then apply the **same fetch → extract `news-news-box` → translate → persist** pipeline. Runs must remain **idempotent**: re-running backfill skips already-stored blobs unless **force refresh** is explicitly requested.
- **Rate & scope controls:** Backfill supports **max pages per invocation**, **concurrency caps**, and **dry-run** (discover-only, no blobs) so operators can validate coverage before burning quota.
- **Observability for backfill:** Counters for listing pages walked, posts discovered vs skipped, pagination stop reason.

### HTTP fetching & mimicry

- All HTTP requests MUST use **configurable outbound headers** stored in secure configuration (Key Vault → app settings references), minimally:
  - `User-Agent` (required configurable default)
  - Optional: `Accept-Language`, `Accept`, `Referer`, custom headers required by resilience or CDN behavior
- **Rate limiting / backoff:** Polite scraping with jittered retries on transient failures; respect server signals (429/503).
- **Encoding:** Explicit handling for UTF-8 and **GB2312/GBK** if the origin serves legacy encodings (common on some `.gov.cn` pages).

### Data capture & content model

- **Discovery:** Crawl configured **list/index URL(s)**; parse article links; dedupe against already-stored post IDs. **Historical mode** extends this to **all listing pages** until the site's pagination ends (see **Crawl modes** above).
- **Primary content selector:** On article pages, the element whose **CSS class is `news-news-box`** is the **authoritative region** for content to **persist and send to translation** (inner subtree: headings, paragraphs, lists, etc.). Implementation should target this class (e.g. `.news-news-box`) as the default extractor; if that node is **missing or empty** after fetch, log a structured warning and fall back to a documented secondary strategy (e.g. configurable override selector or full-page HTML for manual triage only — product decision).
- **Per post, persist (minimum):**
  - Raw HTML (or sanitized HTML) as fetched.
  - **Extracted main article body:** HTML fragment (or parallel plain text) taken from **`news-news-box`** as above.
  - **English translation** of that extracted content — **stored separately** alongside the Chinese fragment for audit and QA.
  - Metadata JSON: canonical URL, post ID, **published date** (best-effort extraction), fetched-at (UTC), content hash, source language tag (`zh-CN`), translator service version / model identifier, crawl run ID.
- **Translation quality:**
  - Use a **professional translation pipeline** with deterministic glossary/terminology hooks if recurring domain terms (e.g., policy / “BRI” jargon) repeat.
  - **Do not strip** headings, paragraphs, lists in a way that loses structure; preserve block structure where feasible (Markdown or HTML fragments for bilingual pair).

### Security

- **No hardcoded secrets** — Key Vault references for translation keys if not fully Managed Identity–capable everywhere.
- **Managed Identity + RBAC** least privilege to Blob container(s); separate read/write principals if warranted.
- **VNet egress allowlist:** Only required hosts (origin blog CDN/domain, Azure Storage endpoints, Translator endpoint, ARM/management if required by platform).
- **PII:** If logs might contain URL query params or bodies, redact in logging pipeline.

### End-to-end testing & CI

- **Goal:** Prove the pipeline **discovery → HTTP fetch (with configured headers) → HTML decode → DOM extract (`.news-news-box`) → translate → write blobs + metadata** in a repeatable way before and after releases.
- **Test layers:**
  - **Automated E2E (preferred in CI):** Run against **recorded fixtures** (saved list HTML + article HTML) in-repo or in a test artifact store so CI does **not** depend on live `yidaiyilu.gov.cn` availability; stub translator and storage with **Azurite** (or ephemeral test container) and assert blob layout, hashes, and translated payload shape.
  - **Live smoke / staging E2E (optional cadence):** A gated pipeline or manual job hits **real index + one known article URL** (e.g. example post) with **translation and storage in a non-prod** subscription — allowlisted egress only; used to catch template/CSS changes.
- **Backfill verification:** E2E or integration test covers **multi-page list discovery** using **fixture HTML** that mirrors pagination; assert all article links are collected and none are dropped across pages.
- **Definition of done for a release:** Green unit tests for parsing/extraction + green E2E on fixtures; optional live smoke documented and passing for major changes to selectors or HTTP stack.
- **Downloader verification:** Include tests for "most recent N" ordering and metadata-path parsing; manual validation should confirm bilingual output files exist for the selected N posts.

## Non-goals (initial)

- General-purpose JavaScript rendering of arbitrary SPAs (unless index/post pages require it after smoke tests).
- Automated republishing/transformation for public redistribution without editorial review workflow.

## Open questions

1. **Legal / policy:** Confirm organizational approval to copy and translate this specific site’s content (copyright, robots.txt, organizational policy).
2. **Rendering:** If list or article bodies are empty without browser execution, add **optional** Playwright in a consumption plan–compatible or dedicated compute path — document tradeoffs.
3. **Translation SLA:** Preferred engine (Azure Translator standard vs customized model / glossary-only).
4. **Retention:** Blob lifecycle (e.g., keep raw forever vs tier to cool/archive after N days).
5. **Pagination:** Exact mechanism for the list view (query params, path segments, infinite scroll vs server paging) — document after first reverse-engineering pass; drives backfill completeness.

