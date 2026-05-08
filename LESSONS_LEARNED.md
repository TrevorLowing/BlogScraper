# Lessons Learned

## Scraping blocks and egress investigation

- The initial architecture (Azure Function doing direct scrape) failed at discovery with repeated upstream disconnects, even when request headers were tuned to look browser-like.
- We validated this was not a parser bug by confirming the same URLs worked from local and by reproducing failures specifically from Function-hosted egress.
- A key finding: "same cloud, same region" did not mean "same network behavior." Function Consumption egress and ACI egress produced different outcomes against the target site.
- Running a one-shot Dockerized scraper in ACI was the decisive experiment: it reached list/article pages reliably and completed the crawl path.
- The practical takeaway is to treat web-scraping connectivity as an egress/IP reputation problem first, not only an application-code problem.

## Connectivity and region behavior

- A successful smoke test in one Azure service does not guarantee another service in the same region will behave the same way.
- Validate connectivity with an isolated one-shot container path before refactoring core scraping logic.
- Keep a reproducible network test path (Function vs ACI) so regressions can be diagnosed quickly.

## ACI dispatch reliability

- `az container create --environment-variables` can break JSON-like values containing commas.
- Scalar env vars (`SCRAPER_PIPELINE_*`) are safer for CLI-driven ACI job creation than a raw JSON env payload.
- Keep a status endpoint (`/api/scrape-aci-status`) to avoid blind async job dispatches.
- If scraping reliability depends on ACI egress, treat ACI as the execution plane and Functions as orchestration/triggering only.

## Deployment operations

- `func azure functionapp publish` can overwrite app settings; reapply required settings immediately after publish.
- Scripted post-publish settings reduce repeated operator errors.
- Keep RBAC scoped to required resource groups/registries and verify role propagation timing.

## Region alignment

- Align runtime components (Function, ACI, Storage, Translator, ACR) in the same region where possible.
- Cross-region ACR works but adds complexity and potential performance/availability variance.

## Testing strategy

- Fixture-based tests for parser/discovery/extraction are essential to protect against site template drift.
- Always keep one manual smoke path for end-to-end validation in real Azure.
- Add tests for operational utilities (like downloader ordering and path parsing), not just pipeline code.

## Operator ergonomics

- A lightweight downloader utility is valuable for QA and stakeholder review:
  - quickly inspect Chinese vs translated artifacts
  - verify metadata and translation quality
  - support audits without needing direct Blob tooling
- Include publish-date capture in metadata and downstream filenames to improve traceability for reviewers.
