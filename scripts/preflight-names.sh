#!/usr/bin/env bash
set -euo pipefail

# Validate Azure resource naming inputs before deployment.
# Usage:
#   ./scripts/preflight-names.sh <rg> <function-app-name> <storage-account> <acr-name> <aci-group>

RG="${1:?resource group name required}"
FUNC_APP="${2:?function app name required}"
STORAGE="${3:?storage account name required}"
ACR_NAME="${4:?acr name required}"
ACI_GROUP="${5:?aci container group name required}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

pass() {
  echo "OK: $*"
}

check_regex() {
  local value="$1"
  local regex="$2"
  local msg="$3"
  if [[ ! "$value" =~ $regex ]]; then
    fail "$msg (value: $value)"
  fi
}

check_len() {
  local value="$1"
  local min="$2"
  local max="$3"
  local field="$4"
  local n="${#value}"
  if (( n < min || n > max )); then
    fail "$field length must be between $min and $max (value: $value, len: $n)"
  fi
}

# Resource Group
check_len "$RG" 1 90 "Resource group"
check_regex "$RG" '^[[:alnum:]_.() -]+$' "Resource group contains invalid characters"
pass "Resource group format"

# Function App
check_len "$FUNC_APP" 2 60 "Function app"
check_regex "$FUNC_APP" '^[a-z0-9-]+$' "Function app must be lowercase letters/numbers/hyphen only"
pass "Function app format"

# Storage account
check_len "$STORAGE" 3 24 "Storage account"
check_regex "$STORAGE" '^[a-z0-9]+$' "Storage account must be lowercase letters/numbers only"
pass "Storage account format"

# ACR
check_len "$ACR_NAME" 5 50 "ACR name"
check_regex "$ACR_NAME" '^[a-zA-Z0-9]+$' "ACR name must be alphanumeric only"
pass "ACR format"

# ACI group
check_len "$ACI_GROUP" 1 63 "ACI group"
check_regex "$ACI_GROUP" '^[a-z0-9-]+$' "ACI group must be lowercase letters/numbers/hyphen only"
pass "ACI group format"

if az account show >/dev/null 2>&1; then
  echo "Checking ACR global availability with Azure..."
  ACR_AVAIL="$(az acr check-name -n "$ACR_NAME" --query nameAvailable -o tsv || echo "unknown")"
  if [[ "$ACR_AVAIL" == "true" ]]; then
    pass "ACR name is available globally"
  elif [[ "$ACR_AVAIL" == "false" ]]; then
    fail "ACR name is not available globally: $ACR_NAME"
  else
    echo "WARN: Could not determine ACR availability (continuing)."
  fi
else
  echo "WARN: Azure CLI not logged in; skipped ACR availability check."
fi

echo "Preflight checks passed."
