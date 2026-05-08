#!/usr/bin/env bash
set -euo pipefail
#
# Step 2 — Grant the Function App system-assigned identity permission to dispatch ACI and pull from ACR.
#
# Enables identity if absent, then assigns:
#   - Contributor on the resource group used for Azure Container Instances (create/update/delete container groups).
#   - AcrPull on the specified Container Registry resource.
#
# Usage:
#   ./scripts/grant-functions-msi-aci-rbac.sh <function-app-name> <function-rg> <aci-dispatch-rg> <acr-name> <acr-rg>
#
# Example:
#   ./scripts/grant-functions-msi-aci-rbac.sh blogscrapr-hpq7ijsgrnt32 blog-scraper-wus2 \\
#       blog-scraper-aci-smoke blogscrapracixyz blog-scraper-aci-smoke
#
SUB="$(az account show --query id -o tsv)"
FUN_APP="${1:?function app name}"
FUN_RG="${2:?function resource group}"
ACI_RG="${3:?ACI dispatch resource group (where container groups live)}"
ACR_NAME="${4:?ACR registry name}"
ACR_RG="${5:?ACR resource group}"

principal="$(az functionapp identity show -g "$FUN_RG" -n "$FUN_APP" --query principalId -o tsv 2>/dev/null || true)"
if [[ -z "${principal:-}" ]] || [[ "$principal" == "None" ]] || [[ "$principal" == "null" ]]; then
  echo "Enabling system-assigned managed identity on $FUN_APP ..."
  az functionapp identity assign -g "$FUN_RG" -n "$FUN_APP" --output none
  principal="$(az functionapp identity show -g "$FUN_RG" -n "$FUN_APP" --query principalId -o tsv)"
fi

SCOPE_DISPATCH="/subscriptions/$SUB/resourceGroups/$ACI_RG"
ACR_SCOPE="$(az acr show -g "$ACR_RG" -n "$ACR_NAME" --query id -o tsv)"

echo "Assign Contributor on $SCOPE_DISPATCH to $principal"
if ! az role assignment create \
  --assignee "$principal" \
  --role "Contributor" \
  --scope "$SCOPE_DISPATCH" \
  --output none 2>/dev/null; then
  echo "  (Contributor assignment may already exist — continuing)"
fi

echo "Assign AcrPull on registry to $principal"
if ! az role assignment create \
  --assignee "$principal" \
  --role AcrPull \
  --scope "$ACR_SCOPE" \
  --output none 2>/dev/null; then
  echo "  (AcrPull assignment may already exist — continuing)"
fi

echo "Propagation can take ~1 minute. Next (order step 3): ./scripts/post-publish-aci-dispatch.sh ..."
