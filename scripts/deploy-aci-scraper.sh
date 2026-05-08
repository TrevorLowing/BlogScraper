#!/usr/bin/env bash
set -euo pipefail

# Build docker/Dockerfile.scraper in Azure Container Registry (context = repo root).
#
# Usage:
#   ACR_NAME=... ACR_RG=... ./scripts/deploy-aci-scraper.sh
#
# Optional:
#   IMAGE_NAME (default blog-scraper-runner)
#   IMAGE_TAG (default v1)
#
# After build, deploy a one-shot group with az container create — pass the same blob/translator/blog
# settings as Functions (prefer --secure-environment-variables for secrets).

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ACR_NAME="${ACR_NAME:?Set ACR_NAME (short name)}"
ACR_RG="${ACR_RG:?Set ACR_RG for the registry}"
IMAGE_NAME="${IMAGE_NAME:-blog-scraper-runner}"
IMAGE_TAG="${IMAGE_TAG:-v1}"

echo "Building ${IMAGE_NAME}:${IMAGE_TAG} in $ACR_NAME (rg=$ACR_RG)"

az acr build \
  --registry "$ACR_NAME" \
  --resource-group "$ACR_RG" \
  --file docker/Dockerfile.scraper \
  --image "${IMAGE_NAME}:${IMAGE_TAG}" \
  "$ROOT"

echo "Built ${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"
