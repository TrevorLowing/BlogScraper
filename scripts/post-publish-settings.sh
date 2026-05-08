#!/usr/bin/env bash
set -euo pipefail
# Reapply settings after `func azure functionapp publish` (publish can reset app settings).
# Usage: ./scripts/post-publish-settings.sh <function-app-name>
# Env:
#   AZ_RG — Function App resource group (default blog-scraper-wus2)
#   AZ_TRANSLATOR_RG — Cognitive Services resource group for translator keys (default blog-scraper-wus2)
#   AZ_TRANSLATOR_ACCOUNT — Translator account name (default blogscraprtrwus2)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RG="${AZ_RG:-blog-scraper-wus2}"
TRG="${AZ_TRANSLATOR_RG:-blog-scraper-wus2}"
TR="${AZ_TRANSLATOR_ACCOUNT:-blogscraprtrwus2}"
APP="${1:?Usage: $0 <function-app-name>}"

KEY="$(az cognitiveservices account keys list -g "$TRG" -n "$TR" --query key1 -o tsv)"

az functionapp config appsettings set -g "$RG" -n "$APP" --settings \
  "TRANSLATOR_ENDPOINT=https://api.cognitive.microsofttranslator.com" \
  "TRANSLATOR_REGION=westus2" \
  "TRANSLATOR_KEY=${KEY}" \
  "HTTP_USER_AGENT=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" \
  "SCRAPE_TIMEOUT_SECONDS=120" \
  --output none

echo "App settings restored on ${APP}: TRANSLATOR_*, HTTP_USER_AGENT, SCRAPE_TIMEOUT_SECONDS."
echo "Optional step 3: export ACI_* then ./scripts/post-publish-aci-dispatch.sh \"$APP\""
