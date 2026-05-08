# Deployment Guide (New Azure Environment)

This guide bootstraps BlogScraper into a fresh Azure subscription/resource group.

## 1) Prerequisites

- Azure subscription with quota for Function App plan in target region
- Azure CLI logged in: `az login`
- Azure Functions Core Tools v4 (`func`)
- Python 3.11+
- Docker access (if building/pushing ACI scraper image)

Optional but recommended:

- `jq` for local JSON inspection

## 2) Required Azure Resources

Minimum runtime resources:

- Resource Group for Function App and base infra
- Function App (Python)
- Storage account/container for scraper artifacts
- Translator (Azure AI Translator)

If using ACI dispatch (recommended for scrape reliability):

- Separate Resource Group for ACI jobs
- Azure Container Registry (ACR)
- ACI-capable region

## 3) One-command Infra + Publish

From repo root:

```bash
LOCATION=westus2 RG=blog-scraper-wus2 ./scripts/deploy-infra-and-publish.sh
```

What this script does:

- Creates/ensures the resource group
- Deploys Bicep (`infra/main.bicep`)
- Publishes Function code with remote build
- Reapplies post-publish app settings via `scripts/post-publish-settings.sh`

## 4) Core App Settings (Function App)

`scripts/post-publish-settings.sh` restores key settings after publish. Required values include:

- `TRANSLATOR_ENDPOINT`
- `TRANSLATOR_REGION`
- `TRANSLATOR_KEY`
- `HTTP_USER_AGENT`
- `SCRAPE_TIMEOUT_SECONDS`

Other common settings:

- `BLOG_SITE_BASE` (default `https://www.yidaiyilu.gov.cn`)
- `BLOG_INDEX_PATH` (default `/list/w/xmzb`)
- `BLOG_INDEX_PATHS` (optional comma-separated additional list paths)
- `BLOG_SCRAPER_TARGETS_JSON` (optional full multi-target JSON override)
- `BLOB_CONTAINER_NAME`
- `SCRAPER_TIMER_SCHEDULE`

## 5) ACI Setup (Docker execution plane)

### 5.1 Build and push scraper image

```bash
ACR_NAME=<acr-name> ACR_RG=<acr-rg> ./scripts/deploy-aci-scraper.sh
```

### 5.2 Grant Function MSI permissions

```bash
./scripts/grant-functions-msi-aci-rbac.sh \
  <function-app-name> <function-rg> <aci-rg> <acr-name> <acr-rg>
```

This grants:

- `Contributor` on ACI dispatch resource group
- `AcrPull` on ACR

### 5.3 Configure Function to dispatch ACI

```bash
export AZ_RG=<function-rg>
export ACI_RESOURCE_GROUP=<aci-rg>
export ACI_LOCATION=westus2
export ACI_IMAGE=<acr-login-server>/blog-scraper-runner:v1
export ACI_REGISTRY_USERNAME=<acr-username>
export ACI_REGISTRY_PASSWORD=<acr-password>
export ACI_SCHEDULED=false

./scripts/post-publish-aci-dispatch.sh <function-app-name>
```

Set `ACI_SCHEDULED=true` only after HTTP dispatch smoke tests pass.

## 6) Install/Run Locally (for dev/test)

```bash
pip install -r requirements.txt
cp local.settings.json.example local.settings.json
pytest -q
```

`local.settings.json.example` shows the full config surface.

## 7) Verification / Smoke Tests

Function HTTP scrape:

```bash
./scripts/smoke-http-azure.sh <function-app-name> <function-rg>
```

ACI full-pipeline smoke:

```bash
./scripts/run-aci-full-pipeline-smoke.sh
```

Downloader check:

```bash
python scripts/download_recent_posts.py --limit 10 --output-dir downloads/recent-posts --include-raw-html
```

## 8) Common Pitfalls

- `func publish` can overwrite app settings; rerun post-publish settings scripts.
- Translator throttling (`429`) can occur under burst load; retry/backoff is implemented.
- Service egress behavior can differ: Function direct scrape may be blocked while ACI succeeds.
- Keep ACR/ACI/Function in aligned regions where possible for simpler operations.

## 9) Recommended Bootstrap Order

1. Deploy infra + publish Function.
2. Reapply core settings.
3. Build/push ACI image.
4. Grant MSI RBAC.
5. Apply ACI dispatch settings (`ACI_SCHEDULED=false`).
6. Run HTTP + ACI smoke tests.
7. Enable `ACI_SCHEDULED=true` for timer offload.

## 10) Copy/Paste Bootstrap Checklist (WUS2 naming pattern)

Use this when cloning the same topology with familiar names.

```bash
# 0) Variables
export LOCATION=westus2
export RG=blog-scraper-wus2
export ACI_RG=blog-scraper-aci-wus2
export ACR_NAME=blogscraprwus2acr
export ACR_RG=blog-scraper-aci-wus2

# 1) Login + subscription
az login
az account show -o table

# 2) Deploy Function infra and publish code
LOCATION=$LOCATION RG=$RG ./scripts/deploy-infra-and-publish.sh

# 3) Discover function app name (if needed)
az functionapp list -g "$RG" --query "[].name" -o tsv
export FUNC_APP="<paste-function-app-name>"

# 4) Build/push ACI runner image
ACR_NAME=$ACR_NAME ACR_RG=$ACR_RG ./scripts/deploy-aci-scraper.sh

# 5) Get ACR login server + credentials
export ACR_SERVER="$(az acr show -g "$ACR_RG" -n "$ACR_NAME" --query loginServer -o tsv)"
export ACI_IMAGE="$ACR_SERVER/blog-scraper-runner:v1"
export ACI_REGISTRY_USERNAME="$(az acr credential show -n "$ACR_NAME" --query username -o tsv)"
export ACI_REGISTRY_PASSWORD="$(az acr credential show -n "$ACR_NAME" --query passwords[0].value -o tsv)"

# 6) Grant Function managed identity RBAC for ACI + ACR pull
./scripts/grant-functions-msi-aci-rbac.sh "$FUNC_APP" "$RG" "$ACI_RG" "$ACR_NAME" "$ACR_RG"

# 7) Apply ACI dispatch settings (keep scheduled off until smoke passes)
export AZ_RG="$RG"
export ACI_RESOURCE_GROUP="$ACI_RG"
export ACI_LOCATION="$LOCATION"
export ACI_SCHEDULED=false
./scripts/post-publish-aci-dispatch.sh "$FUNC_APP"

# 8) Smoke test HTTP path and ACI path
./scripts/smoke-http-azure.sh "$FUNC_APP" "$RG"
./scripts/run-aci-full-pipeline-smoke.sh

# 9) Optional: enable timer offload to ACI after validation
az functionapp config appsettings set -g "$RG" -n "$FUNC_APP" --settings ACI_SCHEDULED=true
```

## 11) Copy/Paste Checklist (New Region + env suffix)

Use this for clean `dev` / `prod` style environments in any supported region.

```bash
# 0) Choose region + environment
export LOCATION=eastus2
export ENV=dev # dev | prod
export RG="blog-scraper-${LOCATION}-${ENV}"
export ACI_RG="blog-scraper-aci-${LOCATION}-${ENV}"
export ACR_NAME="blogscrapr${LOCATION}${ENV}acr" # must be globally unique, lowercase/no dashes
export ACR_RG="$ACI_RG"

# 1) Login + select subscription
az login
az account show -o table

# 2) Ensure ACI resource group exists
az group create -n "$ACI_RG" -l "$LOCATION"

# 3) Deploy Function infra and publish code
LOCATION="$LOCATION" RG="$RG" ./scripts/deploy-infra-and-publish.sh

# 4) Get Function app name
az functionapp list -g "$RG" --query "[].name" -o tsv
export FUNC_APP="<paste-function-app-name>"

# 5) Create ACR if missing
az acr show -n "$ACR_NAME" -g "$ACR_RG" >/dev/null 2>&1 || \
  az acr create -n "$ACR_NAME" -g "$ACR_RG" --sku Basic --admin-enabled true

# 6) Build/push scraper image
ACR_NAME="$ACR_NAME" ACR_RG="$ACR_RG" ./scripts/deploy-aci-scraper.sh

# 7) Export ACR values used by Function ACI dispatcher settings
export ACR_SERVER="$(az acr show -g "$ACR_RG" -n "$ACR_NAME" --query loginServer -o tsv)"
export ACI_IMAGE="$ACR_SERVER/blog-scraper-runner:v1"
export ACI_REGISTRY_USERNAME="$(az acr credential show -n "$ACR_NAME" --query username -o tsv)"
export ACI_REGISTRY_PASSWORD="$(az acr credential show -n "$ACR_NAME" --query passwords[0].value -o tsv)"

# 8) Grant MSI permissions
./scripts/grant-functions-msi-aci-rbac.sh "$FUNC_APP" "$RG" "$ACI_RG" "$ACR_NAME" "$ACR_RG"

# 9) Apply ACI settings (start with scheduled disabled)
export AZ_RG="$RG"
export ACI_RESOURCE_GROUP="$ACI_RG"
export ACI_LOCATION="$LOCATION"
export ACI_SCHEDULED=false
./scripts/post-publish-aci-dispatch.sh "$FUNC_APP"

# 10) Validate paths
./scripts/smoke-http-azure.sh "$FUNC_APP" "$RG"
./scripts/run-aci-full-pipeline-smoke.sh

# 11) Enable timer -> ACI after validation
az functionapp config appsettings set -g "$RG" -n "$FUNC_APP" --settings ACI_SCHEDULED=true
```

## 12) Naming Constraints (quick reference)

Use this to avoid first-run deployment failures caused by invalid names.

| Resource | Key constraints | Example |
|---|---|---|
| Resource Group | 1-90 chars; letters, numbers, `_`, `-`, `.`, `(`, `)` | `blog-scraper-eastus2-dev` |
| Function App name | Globally unique; 2-60 chars; lowercase letters/numbers/hyphen | `blogscrapr-eastus2-dev` |
| Storage account | Globally unique; 3-24 chars; lowercase letters/numbers only | `blogscrapreus2devsa` |
| ACR name | Globally unique; 5-50 chars; alphanumeric only (no dashes) | `blogscrapreastus2devacr` |
| ACI container group | 1-63 chars; lowercase letters/numbers/hyphen | `aci-bs-eastus2-dev-01` |

Practical tips:

- Keep names short early (`blogscrapr...`) to preserve room for region/env suffixes.
- Avoid random punctuation; many resources reject `_` or `.` even if RG allows them.
- Check global uniqueness before long scripts:
  - `az acr check-name -n <acr-name>`
  - `az functionapp list --query \"[].name\" -o tsv` (for your subscription visibility)

Optional preflight helper:

```bash
./scripts/preflight-names.sh \
  <resource-group> <function-app-name> <storage-account> <acr-name> <aci-group-name>
```
