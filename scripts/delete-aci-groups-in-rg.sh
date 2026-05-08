#!/usr/bin/env bash
set -euo pipefail
# Delete container groups in one resource group by name, or delete all groups in that RG.
#
#   ACI_RG=blog-scraper-aci-smoke ./scripts/delete-aci-groups-in-rg.sh
#   ACI_RG=blog-scraper-aci-smoke ./scripts/delete-aci-groups-in-rg.sh aci-bs-foo aci-bs-bar

RG="${ACI_RG:?Set ACI_RG to the container-instances resource group}"

if (($#)); then
  for n in "$@"; do
    echo "Deleting $n ..."
    az container delete -g "$RG" -n "$n" --yes --output none || true
  done
else
  names="$(az container list -g "$RG" --query "[].name" -o tsv 2>/dev/null || true)"
  if [[ -z "${names// /}" ]]; then
    echo "No container groups in $RG."
    exit 0
  fi
  while IFS= read -r n; do
    [[ -z "$n" ]] && continue
    echo "Deleting $n ..."
    az container delete -g "$RG" -n "$n" --yes --output none || true
  done <<< "$names"
fi
