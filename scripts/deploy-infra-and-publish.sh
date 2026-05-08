#!/usr/bin/env bash
set -euo pipefail
# Azure prerequisites: usable App Service quota in the chosen region (Y1 Dynamic or B1 Basic).
# East US often had Y1/B1 at 0 while westus2 validated—override LOCATION if needed.
# For Application Insights set enableAppInsights=true only after registering
# microsoft.operationalinsights ( az provider register -n Microsoft.OperationalInsights ).
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

LOCATION="${LOCATION:-westus2}"
RG="${RG:-blog-scraper-wus2}"

echo "Ensure resource group: $RG ($LOCATION)"
az group create --name "$RG" --location "$LOCATION" --output none

echo "Deploying Bicep (infra/main.bicep)..."
DEPLOY="$(az deployment group create \
  --resource-group "$RG" \
  --name "blogscrap-$(date +%s)" \
  --template-file "$ROOT/infra/main.bicep" \
  --parameters location="$LOCATION" hostPlan=Dynamic enableAppInsights=false \
  --query 'properties.outputs' \
  --output json)"

FUNC_NAME="$(echo "$DEPLOY" | python3 -c "import sys, json; print(json.load(sys.stdin)['functionAppName']['value'])")"

echo ""
echo "Deployed function app: $FUNC_NAME"
echo "Publishing Python package (includes remote build)..."

command -v func >/dev/null 2>&1 || {
  echo "Install Azure Functions Core Tools: brew tap azure/functions && brew install azure-functions-core-tools@4" >&2
  exit 1
}

func azure functionapp publish "$FUNC_NAME" --python --build remote

AZ_RG="$RG" AZ_TRANSLATOR_RG="${AZ_TRANSLATOR_RG:-blog-scraper-wus2}" \
  "$ROOT/scripts/post-publish-settings.sh" "$FUNC_NAME"

echo ""
echo "Done."
echo "  Host: https://${FUNC_NAME}.azurewebsites.net"
echo '  Smoke: POST https://'"${FUNC_NAME}"'.azurewebsites.net/api/scrape (Function key required)'
echo "  Optional — ACI dispatch env: export AZ_RG=$RG + ACI_* registry creds, then"
echo "       ./scripts/post-publish-aci-dispatch.sh $FUNC_NAME"
