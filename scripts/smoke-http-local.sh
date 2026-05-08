#!/usr/bin/env bash
set -euo pipefail
BASE="${FUNC_BASE_URL:-http://127.0.0.1:7071}"

if ! curl -sf -o /dev/null "$BASE" 2>/dev/null; then
  echo "Host not reachable at $BASE — start Functions (and Azurite) first:"
  echo "  npx --yes azurite --skipApiVersionCheck --silent --location .azurite 2>.azurite/azurite.err &"
  echo "  source .venv/bin/activate && func start"
  exit 1
fi

echo "=== Incremental dry_run, max 1 article ==="
curl -sS -X POST "$BASE/api/scrape" \
  -H "Content-Type: application/json" \
  -d '{"mode":"incremental","max_posts":1,"dry_run":true}'
echo ""

echo ""
echo "=== Historical dry_run, 2 pages, max 12 posts ==="
curl -sS -X POST "$BASE/api/scrape" \
  -H "Content-Type: application/json" \
  -d '{"mode":"historical","max_pages":2,"max_posts":12,"dry_run":true}'
echo ""
