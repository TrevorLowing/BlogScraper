#!/usr/bin/env bash
set -euo pipefail
# Production smoke against deployed Function App (requires Azure CLI login).
RG="${AZ_RG:-blog-scraper-wus2}"
APP="${AZ_FUNCTION_APP:-blogscrapr-hpq7ijsgrnt32}"
BASE_URL="${AZ_FUNC_URL:-https://${APP}.azurewebsites.net}"

FK="$(az functionapp function keys list -g "$RG" -n "$APP" --function-name scrape_http --query default -o tsv)"

echo "POST ${BASE_URL}/api/scrape (incremental, dry_run, max_posts=1)"
curl -sS -w "\nHTTP:%{http_code}\n" -X POST "${BASE_URL}/api/scrape?code=${FK}" \
  -H "Content-Type: application/json" \
  -d '{"mode":"incremental","max_posts":1,"dry_run":true}'
echo ""
