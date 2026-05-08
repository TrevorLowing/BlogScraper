#!/usr/bin/env bash
set -euo pipefail
# Build image in Azure Container Registry and run a one-shot Azure Container Instances job
# to test outbound HTTP to TARGET_URL from Azure container egress (different pool than Functions).
#
# Prerequisites: az login; providers Microsoft.ContainerRegistry, Microsoft.ContainerInstance registered.
#
# Usage:
#   ./scripts/run-aci-smoke.sh
# Env overrides:
#   ACI_RG (default blog-scraper-aci-smoke)
#   LOCATION (default eastasia)
#   TARGET_URL (default https://www.yidaiyilu.gov.cn/list/w/xmzb)

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCKER_CTX="$ROOT/docker"

ACI_RG="${ACI_RG:-blog-scraper-aci-smoke}"
LOCATION="${LOCATION:-eastasia}"
TARGET_URL="${TARGET_URL:-https://www.yidaiyilu.gov.cn/list/w/xmzb}"
SUFFIX="$(openssl rand -hex 3)"
ACR_NAME="${ACR_NAME:-blogscrapraci${SUFFIX}}"
IMAGE_NAME="smoke-fetch"
IMAGE_TAG="v1"
CONTAINER_GROUP="${CONTAINER_GROUP:-aci-smoke-${SUFFIX}}"

echo "RG=$ACI_RG LOCATION=$LOCATION ACR=$ACR_NAME container=$CONTAINER_GROUP"

az group create --name "$ACI_RG" --location "$LOCATION" --output none

echo "Creating Azure Container Registry (Basic)..."
az acr create \
  --resource-group "$ACI_RG" \
  --name "$ACR_NAME" \
  --sku Basic \
  --admin-enabled true \
  --output none

echo "Building image in ACR (this may take a few minutes)..."
# Run build from docker/ so Dockerfile path resolves correctly for remote builder.
(
  cd "$DOCKER_CTX"
  az acr build \
    --registry "$ACR_NAME" \
    --resource-group "$ACI_RG" \
    --image "${IMAGE_NAME}:${IMAGE_TAG}" \
    --file Dockerfile \
    .
)

FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"
ACR_USER="$(az acr credential show -n "$ACR_NAME" --query username -o tsv)"
ACR_PASS="$(az acr credential show -n "$ACR_NAME" --query 'passwords[0].value' -o tsv)"

echo "Starting ACI one-shot container..."
az container create \
  --resource-group "$ACI_RG" \
  --name "$CONTAINER_GROUP" \
  --image "$FULL_IMAGE" \
  --registry-login-server "${ACR_NAME}.azurecr.io" \
  --registry-username "$ACR_USER" \
  --registry-password "$ACR_PASS" \
  --os-type Linux \
  --restart-policy Never \
  --cpu 1 \
  --memory 1 \
  --environment-variables TARGET_URL="$TARGET_URL" \
  --output none

echo "Waiting for container to finish..."
for _ in $(seq 1 60); do
  STATE="$(az container show -g "$ACI_RG" -n "$CONTAINER_GROUP" --query "containers[0].instanceView.currentState.state" -o tsv 2>/dev/null || echo Pending)"
  echo "  state=$STATE"
  if [[ "$STATE" == "Terminated" ]] || [[ "$STATE" == "Failed" ]]; then
    break
  fi
  sleep 5
done

echo ""
echo "===== LOGS ====="
az container logs --resource-group "$ACI_RG" --name "$CONTAINER_GROUP" || true

echo ""
EXIT_CODE="$(az container show -g "$ACI_RG" -n "$CONTAINER_GROUP" --query "containers[0].instanceView.exitCode" -o tsv 2>/dev/null || echo "")"
echo "Exit code (if reported): $EXIT_CODE"

echo ""
echo "To remove resources when done: az group delete -n $ACI_RG --yes --no-wait"
