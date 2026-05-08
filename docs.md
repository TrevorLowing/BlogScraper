# BlogScraper Utilities and Docs Index

- Product requirements: `BlogScraper-PRD.md`
- Architecture and flow: `ARCHITECTURE_AND_FLOW.md`
- Lessons learned: `LESSONS_LEARNED.md`
- Deployment guide: `DEPLOYMENT.md`
- Changelog: `CHANGELOG.md`

## Downloader utility

Download the most recent Chinese + English artifacts from Blob Storage:

```bash
python scripts/download_recent_posts.py \
  --limit 10 \
  --output-dir downloads/recent-posts
```

### Options

- `--connection-string`: override storage connection string
- `--container`: blob container name (default `blog-scraper`)
- `--limit`: number of recent posts (default `10`)
- `--output-dir`: local target directory
- `--include-raw-html`: also download `raw.html`

### Environment fallbacks

- `BLOG_SCRAPER_STORAGE`
- `AzureWebJobsStorage`
- `BLOB_CONTAINER_NAME`
