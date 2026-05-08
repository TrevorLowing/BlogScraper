#!/usr/bin/env bash
set -euo pipefail
#
# Step 1 — Full scraper pipeline on ACI (order: build image, then run one-shot container group).
#
# Prerequisites: az login; Microsoft.ContainerRegistry + Microsoft.ContainerInstance registered.
#
# Usage:
#   export ACR_NAME=... ACR_RG=...
#   export ACI_RG=blog-scraper-aci-smoke   # RG where the container group is created (created if missing)
#   Optional: SKIP_BUILD=1 to reuse existing image tag in ACR
#   Optional: BLOG_INDEX_PATHS / BLOG_SCRAPER_TARGETS_JSON (same semantics as Functions env)
#
# Safe default: incremental, one post, dry_run via SCRAPER_PIPELINE_* (no commas — ``az
# container create --environment-variables`` splits on commas inside values).
#
# Optional: set PIPELINE_OPTIONS_JSON only if you use a deployment path that preserves it
# (SDK/ARM). This script omits it by default.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ACR_NAME="${ACR_NAME:?export ACR_NAME}"
ACR_RG="${ACR_RG:?export ACR_RG}"
ACI_RG="${ACI_RG:?export ACI_RG (resource group for container instances)}"
LOCATION="${LOCATION:-eastasia}"
IMAGE_NAME="${IMAGE_NAME:-blog-scraper-runner}"
IMAGE_TAG="${IMAGE_TAG:-v1}"
SKIP_BUILD="${SKIP_BUILD:-0}"
SUFFIX="$(openssl rand -hex 4)"
CONTAINER_GROUP="${CONTAINER_GROUP:-aci-bs-${SUFFIX}}"

BLOG_SITE_BASE="${BLOG_SITE_BASE:-https://www.yidaiyilu.gov.cn}"
BLOG_INDEX_PATH="${BLOG_INDEX_PATH:-/list/w/xmzb}"
SCRAPER_PIPELINE_MODE="${SCRAPER_PIPELINE_MODE:-incremental}"
SCRAPER_PIPELINE_DRY_RUN="${SCRAPER_PIPELINE_DRY_RUN:-true}"
SCRAPER_PIPELINE_MAX_POSTS="${SCRAPER_PIPELINE_MAX_POSTS:-1}"

_dry_lc="$(printf '%s' "${SCRAPER_PIPELINE_DRY_RUN:-}" | tr '[:upper:]' '[:lower:]')"
if [[ "$_dry_lc" != "true" && "$_dry_lc" != "1" && "$_dry_lc" != "yes" && "$_dry_lc" != "on" ]]; then
  if [[ -z "${BLOG_SCRAPER_STORAGE:-}" ]]; then
    echo "Set BLOG_SCRAPER_STORAGE or SCRAPER_PIPELINE_DRY_RUN=true (or yes/1/on)."
    exit 2
  fi
fi

echo "STEP 1a: RG=$ACI_RG LOCATION=$LOCATION IMAGE=${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"

az group create --name "$ACI_RG" --location "$LOCATION" --output none || true

if [[ "$SKIP_BUILD" != "1" ]]; then
  echo "STEP 1b: Building image in ACR..."
  ACR_NAME="$ACR_NAME" ACR_RG="$ACR_RG" IMAGE_NAME="$IMAGE_NAME" IMAGE_TAG="$IMAGE_TAG" \
    "$ROOT/scripts/deploy-aci-scraper.sh"
else
  echo "SKIP_BUILD=1 — using existing tag ${IMAGE_TAG} in registry."
fi

FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${IMAGE_TAG}"
ACR_USER="$(az acr credential show -n "$ACR_NAME" --query username -o tsv)"
ACR_PASS="$(az acr credential show -n "$ACR_NAME" --query 'passwords[0].value' -o tsv)"

ENV_ARGS=(
  BLOG_SITE_BASE="$BLOG_SITE_BASE"
  BLOG_INDEX_PATH="$BLOG_INDEX_PATH"
  SCRAPER_PIPELINE_MODE="$SCRAPER_PIPELINE_MODE"
  SCRAPER_PIPELINE_DRY_RUN="$SCRAPER_PIPELINE_DRY_RUN"
  SCRAPER_PIPELINE_MAX_POSTS="$SCRAPER_PIPELINE_MAX_POSTS"
)

if [[ -n "${PIPELINE_OPTIONS_JSON:-}" ]]; then ENV_ARGS+=(PIPELINE_OPTIONS_JSON="$PIPELINE_OPTIONS_JSON"); fi
if [[ -n "${BLOG_INDEX_PATHS:-}" ]]; then ENV_ARGS+=(BLOG_INDEX_PATHS="$BLOG_INDEX_PATHS"); fi
if [[ -n "${BLOG_SCRAPER_TARGETS_JSON:-}" ]]; then ENV_ARGS+=(BLOG_SCRAPER_TARGETS_JSON="$BLOG_SCRAPER_TARGETS_JSON"); fi

SEC_ARGS=()
if [[ -n "${BLOB_CONTAINER_NAME:-}" ]]; then ENV_ARGS+=(BLOB_CONTAINER_NAME="$BLOB_CONTAINER_NAME"); fi
if [[ -n "${CONTENT_SELECTORS:-}" ]]; then ENV_ARGS+=(CONTENT_SELECTORS="$CONTENT_SELECTORS"); fi
if [[ -n "${HTTP_USER_AGENT:-}" ]]; then ENV_ARGS+=(HTTP_USER_AGENT="$HTTP_USER_AGENT"); fi

if [[ -n "${TRANSLATOR_ENDPOINT:-}" ]]; then ENV_ARGS+=(TRANSLATOR_ENDPOINT="$TRANSLATOR_ENDPOINT"); fi
if [[ -n "${TRANSLATOR_REGION:-}" ]]; then ENV_ARGS+=(TRANSLATOR_REGION="$TRANSLATOR_REGION"); fi

if [[ -n "${BLOG_SCRAPER_STORAGE:-}" ]]; then SEC_ARGS+=(BLOG_SCRAPER_STORAGE="$BLOG_SCRAPER_STORAGE"); fi
if [[ -n "${TRANSLATOR_KEY:-}" ]]; then SEC_ARGS+=(TRANSLATOR_KEY="$TRANSLATOR_KEY"); fi

echo "STEP 1c: Starting container group $CONTAINER_GROUP"
CREATE_CMD=(
  az container create
  --resource-group "$ACI_RG"
  --name "$CONTAINER_GROUP"
  --image "$FULL_IMAGE"
  --registry-login-server "${ACR_NAME}.azurecr.io"
  --registry-username "$ACR_USER"
  --registry-password "$ACR_PASS"
  --os-type Linux
  --restart-policy Never
  --cpu "${ACI_CPU:-1}"
  --memory "${ACI_MEMORY_GB:-1.5}"
)

if [[ ${#ENV_ARGS[@]} -gt 0 ]]; then
  CREATE_CMD+=(--environment-variables "${ENV_ARGS[@]}")
fi
if [[ ${#SEC_ARGS[@]} -gt 0 ]]; then
  CREATE_CMD+=(--secure-environment-variables "${SEC_ARGS[@]}")
fi

CREATE_CMD+=(--output none)
"${CREATE_CMD[@]}"

echo "Waiting for container to finish..."
for _ in $(seq 1 90); do
  STATE="$(az container show -g "$ACI_RG" -n "$CONTAINER_GROUP" --query 'containers[0].instanceView.currentState.state' -o tsv 2>/dev/null || echo Pending)"
  echo "  state=$STATE"
  if [[ "$STATE" == "Terminated" ]] || [[ "$STATE" == "Failed" ]]; then
    break
  fi
  sleep 5
done

echo ""
echo "===== LOGS ====="
az container logs --resource-group "$ACI_RG" --name "$CONTAINER_GROUP"

EXIT_CODE="$(az container show -g "$ACI_RG" -n "$CONTAINER_GROUP" --query 'containers[0].instanceView.exitCode' -o tsv 2>/dev/null || echo "")"
echo ""
echo "Exit code: ${EXIT_CODE:-unknown}"
echo ""
echo "Next (order step 2): ./scripts/grant-functions-msi-aci-rbac.sh ..."
