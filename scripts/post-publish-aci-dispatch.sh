#!/usr/bin/env bash
set -euo pipefail
#
# Step 3 — Push ACI dispatch settings onto a Function App (after post-publish-settings.sh).
#
# Required env vars (non-secret plain settings):
#   AZ_RG                     — Function app resource group
#   ACI_RESOURCE_GROUP       — RG where container groups should be created
#   ACI_IMAGE                — Full image URL, e.g. myacr.azurecr.io/blog-scraper-runner:v1
#   ACI_LOCATION             — e.g. eastasia
#
# Optional secrets (only needed when not using managed identity pull):
#   ACI_REGISTRY_USERNAME
#   ACI_REGISTRY_PASSWORD
#
# Defaults:
#   ACI_SUBSCRIPTION_ID / AZURE_SUBSCRIPTION_ID filled from az account show if unset
#
# Timer / step 4 — set optional:
#   ACI_SCHEDULED=true   → timer invokes ACI incremental runs instead of in-process pipeline
#

APP="${1:?pass the Function app name as the first argument}"

FUN_RG="${AZ_RG:?Set AZ_RG to the Function App resource group}"
ACI_SUB="${ACI_SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-}}"
if [[ -z "$ACI_SUB" ]]; then
  ACI_SUB="$(az account show --query id -o tsv)"
fi

IMAGE="${ACI_IMAGE:?export ACI_IMAGE (full docker image URI)}"
RG_ACI="${ACI_RESOURCE_GROUP:?export ACI_RESOURCE_GROUP}"
LOC="${ACI_LOCATION:?export ACI_LOCATION}"
REG_SERVER="${ACI_REGISTRY_SERVER:-}"
if [[ -z "${REG_SERVER}" ]] && [[ "$IMAGE" == *"/"* ]]; then
  REG_SERVER="${IMAGE%%/*}"
fi

USE_MI_PULL="${ACI_USE_MANAGED_IDENTITY_PULL:-true}"
REG_USER="${ACI_REGISTRY_USERNAME:-}"
REG_PASS="${ACI_REGISTRY_PASSWORD:-}"
if [[ "$USE_MI_PULL" != "true" && "$USE_MI_PULL" != "1" && "$USE_MI_PULL" != "yes" && "$USE_MI_PULL" != "on" ]]; then
  REG_USER="${ACI_REGISTRY_USERNAME:?export ACI_REGISTRY_USERNAME or set ACI_USE_MANAGED_IDENTITY_PULL=true}"
  REG_PASS="${ACI_REGISTRY_PASSWORD:?export ACI_REGISTRY_PASSWORD or set ACI_USE_MANAGED_IDENTITY_PULL=true}"
fi

CPU="${ACI_CPU:-1}"
MEM="${ACI_MEMORY_GB:-1.5}"
CT_NAME="${ACI_CONTAINER_NAME:-blogscraper}"
SCHED="${ACI_SCHEDULED:-false}"

SETTINGS=(
  "ACI_SUBSCRIPTION_ID=${ACI_SUB}"
  "ACI_RESOURCE_GROUP=${RG_ACI}"
  "ACI_LOCATION=${LOC}"
  "ACI_IMAGE=${IMAGE}"
  "ACI_REGISTRY_SERVER=${REG_SERVER}"
  "ACI_CPU=${CPU}"
  "ACI_MEMORY_GB=${MEM}"
  "ACI_CONTAINER_NAME=${CT_NAME}"
  "ACI_SCHEDULED=${SCHED}"
  "ACI_USE_MANAGED_IDENTITY_PULL=${USE_MI_PULL}"
)
if [[ -n "${REG_USER}" ]]; then SETTINGS+=("ACI_REGISTRY_USERNAME=${REG_USER}"); fi
if [[ -n "${REG_PASS}" ]]; then SETTINGS+=("ACI_REGISTRY_PASSWORD=${REG_PASS}"); fi

az functionapp config appsettings set -g "$FUN_RG" -n "$APP" --settings \
  "${SETTINGS[@]}" \
  --output none

echo "ACI dispatcher settings applied to ${APP} (AZ_RG=${FUN_RG}), ACI_SCHEDULED=${SCHED}."
echo "Step 4: leave ACI_SCHEDULED=false until HTTP tests pass; enable for timer-offload when ready."
