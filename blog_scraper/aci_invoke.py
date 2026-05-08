"""Create one-shot Azure Container Instances jobs that run ``python -m blog_scraper.aci_runner``."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any, Mapping

from azure.identity import DefaultAzureCredential
from azure.mgmt.containerinstance import ContainerInstanceManagementClient
from azure.mgmt.containerinstance.models import (
    Container,
    ContainerGroup,
    ContainerGroupRestartPolicy,
    EnvironmentVariable,
    ImageRegistryCredential,
    OperatingSystemTypes,
    ResourceRequests,
    ResourceRequirements,
)

from blog_scraper.pipeline import PipelineOptions, pipeline_options_to_dict

_LOGGER = logging.getLogger(__name__)

_CONTAINER_CMD = ["python", "-m", "blog_scraper.aci_runner"]

_COPY_ENV_KEYS: tuple[str, ...] = (
    "BLOG_SITE_BASE",
    "BLOG_INDEX_PATH",
    "BLOG_INDEX_PATHS",
    "BLOG_SCRAPER_TARGETS_JSON",
    "BLOG_SCRAPER_STORAGE",
    "AzureWebJobsStorage",
    "BLOB_CONTAINER_NAME",
    "HTTP_USER_AGENT",
    "HTTP_EXTRA_HEADERS_JSON",
    "CONTENT_SELECTORS",
    "BLOG_HTML_EXCLUDE_PATHS",
    "TRANSLATOR_ENDPOINT",
    "TRANSLATOR_KEY",
    "TRANSLATOR_REGION",
    "SCRAPE_TIMEOUT_SECONDS",
    "LOG_LEVEL",
    "ACI_EXIT_NONZERO_ON_ERRORS",
    "SCRAPER_PIPELINE_MODE",
    "SCRAPER_PIPELINE_DRY_RUN",
    "SCRAPER_PIPELINE_FORCE",
    "SCRAPER_PIPELINE_MAX_POSTS",
    "SCRAPER_PIPELINE_MAX_PAGES",
)

_SECURE_ENV_EXACT = frozenset(
    {
        "BLOG_SCRAPER_STORAGE",
        "AZUREWEBJOBSSTORAGE",
        "TRANSLATOR_KEY",
    }
)


def _subscription_id_from_environ() -> str:
    return (
        os.environ.get("ACI_SUBSCRIPTION_ID", "").strip()
        or os.environ.get("AZURE_SUBSCRIPTION_ID", "").strip()
    )


def sanitize_container_group_name(raw: str) -> str:
    s = raw.lower().strip()
    s = re.sub(r"[^a-z0-9-]", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if len(s) < 3:
        s = "aci-bs-" + uuid.uuid4().hex[:10]
    return s[:63]


def env_name_is_sensitive(name: str) -> bool:
    u = name.upper().replace("_", "").replace("-", "")
    if u == "AZUREWEBJOBSSTORAGE" or u == "BLOGSCRAPERSTORAGE":
        return True
    if name in _COPY_ENV_KEYS and name.endswith("_KEY"):
        return True
    return name.upper() in _SECURE_ENV_EXACT


def build_aci_environment_variables(
    pipeline_options: PipelineOptions,
    *,
    extra_plain: Mapping[str, str | None] | None = None,
) -> list[EnvironmentVariable]:
    """Env vars forwarded into the scrape container."""
    blobs: dict[str, tuple[str, bool]] = {}

    for key in _COPY_ENV_KEYS:
        if key not in os.environ:
            continue
        val = os.environ.get(key)
        if val is None or val == "":
            continue
        secure = env_name_is_sensitive(key)
        blobs[key] = (val, secure)

    if extra_plain:
        for k, v in extra_plain.items():
            if v is None or v == "":
                continue
            blobs[str(k)] = (str(v), False)

    dopt = dict(pipeline_options_to_dict(pipeline_options))
    blobs["PIPELINE_OPTIONS_JSON"] = (
        json.dumps(dopt, separators=(",", ":")),
        False,
    )
    blobs["SCRAPER_PIPELINE_MODE"] = (str(dopt["mode"]), False)
    blobs["SCRAPER_PIPELINE_DRY_RUN"] = ("true" if dopt["dry_run"] else "false", False)
    blobs["SCRAPER_PIPELINE_FORCE"] = ("true" if dopt["force"] else "false", False)
    if dopt["max_posts"] is not None:
        blobs["SCRAPER_PIPELINE_MAX_POSTS"] = (str(dopt["max_posts"]), False)
    if dopt["max_pages"] is not None:
        blobs["SCRAPER_PIPELINE_MAX_PAGES"] = (str(dopt["max_pages"]), False)
    envs: list[EnvironmentVariable] = []
    # Deterministic ordering for debugging
    for name in sorted(blobs):
        val, secure = blobs[name]
        if secure:
            envs.append(EnvironmentVariable(name=name, secure_value=str(val)))
        else:
            envs.append(EnvironmentVariable(name=name, value=str(val)))

    return envs


def _aci_client() -> tuple[ContainerInstanceManagementClient, str]:
    sub = _subscription_id_from_environ()
    if not sub:
        raise ValueError("Set ACI_SUBSCRIPTION_ID or AZURE_SUBSCRIPTION_ID for ACI dispatch.")
    cred = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client = ContainerInstanceManagementClient(cred, subscription_id=sub)
    return client, sub


def start_blog_scraper_aci(
    options: PipelineOptions,
    *,
    container_group_name: str | None = None,
    wait: bool = False,
) -> dict[str, Any]:
    """Provision a Container Instance group running the scrape image."""
    rg = os.environ.get("ACI_RESOURCE_GROUP", "").strip()
    location = os.environ.get("ACI_LOCATION", "eastasia").strip()
    image = os.environ.get("ACI_IMAGE", "").strip()
    container_name = os.environ.get("ACI_CONTAINER_NAME", "blogscraper").strip()
    cpu = float(os.environ.get("ACI_CPU", "1"))
    memory_gb = float(os.environ.get("ACI_MEMORY_GB", "1.5"))
    registry_server = os.environ.get("ACI_REGISTRY_SERVER", "").strip()
    registry_user = os.environ.get("ACI_REGISTRY_USERNAME", "").strip()
    registry_password = os.environ.get("ACI_REGISTRY_PASSWORD", "").strip()

    if not rg:
        raise ValueError("ACI_RESOURCE_GROUP must be set.")
    if not image:
        raise ValueError("ACI_IMAGE must be set (e.g. myregistry.azurecr.io/blog-scraper-runner:latest).")

    if "/" in image and not registry_server:
        registry_server = image.split("/", 1)[0]
    is_private_registry = bool(registry_server and registry_server.endswith(".azurecr.io"))
    if is_private_registry and (not registry_user or not registry_password):
        raise ValueError(
            "ACI_REGISTRY_USERNAME and ACI_REGISTRY_PASSWORD must be set for Azure Container Registry images.",
        )

    group_name = container_group_name or sanitize_container_group_name(f"aci-bs-{uuid.uuid4().hex[:12]}")

    env_block = build_aci_environment_variables(options)

    resources = ResourceRequirements(
        requests=ResourceRequests(memory_in_gb=memory_gb, cpu=cpu),
    )

    ctr = Container(
        name=container_name,
        image=image,
        resources=resources,
        command=_CONTAINER_CMD,
        environment_variables=env_block,
    )

    credentials: list[ImageRegistryCredential] | None = None
    if registry_server and registry_user and registry_password:
        credentials = [
            ImageRegistryCredential(server=registry_server, username=registry_user, password=registry_password),
        ]

    cgroup = ContainerGroup(
        location=location,
        containers=[ctr],
        os_type=OperatingSystemTypes.LINUX,
        restart_policy=ContainerGroupRestartPolicy.NEVER,
        image_registry_credentials=credentials,
    )

    client, sub = _aci_client()

    kwargs: dict[str, Any] = {}
    if wait:
        kwargs["polling"] = True
    else:
        kwargs["polling"] = False

    _LOGGER.info("Starting ACI group=%s rg=%s image=%s wait=%s", group_name, rg, image, wait)
    client.container_groups.begin_create_or_update(
        rg,
        group_name,
        cgroup,
        **kwargs,
    )

    return {
        "subscription_id": sub,
        "resource_group": rg,
        "location": location,
        "container_group_name": group_name,
        "container_name": container_name,
        "image": image,
        "provision_async": not wait,
    }


def fetch_aci_job_status(container_group_name: str | None, *, resource_group: str | None = None) -> dict[str, Any]:
    """Inspect provisioning state + container instance view for a scrape job."""
    rg = (resource_group or os.environ.get("ACI_RESOURCE_GROUP") or "").strip()
    ctr_name = os.environ.get("ACI_CONTAINER_NAME", "blogscraper").strip()
    if not container_group_name or not rg:
        raise ValueError("container_group_name and resource group are required.")

    client, _ = _aci_client()
    cg = client.container_groups.get(rg, container_group_name)

    state: str | None = None
    exit_code: int | None = None
    for c in cg.containers or []:
        if getattr(c, "name", None) == ctr_name or len(cg.containers or []) == 1:
            iv = getattr(c, "instance_view", None)
            cur = getattr(iv, "current_state", None) if iv else None
            state = getattr(cur, "state", None) if cur else None
            exit_code = getattr(cur, "exit_code", None) if cur else None
            break

    logs_text: str | None = None
    try:
        logs = client.containers.list_logs(rg, container_group_name, ctr_name, tail=200)
        logs_text = getattr(logs, "content", None)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("Logs not available yet: %s", exc)

    return {
        "subscription_id": _subscription_id_from_environ(),
        "resource_group": rg,
        "container_group_name": container_group_name,
        "provisioning_state": getattr(cg, "provisioning_state", None),
        "instance_state": state,
        "exit_code": exit_code,
        "logs_tail": logs_text,
    }


def delete_aci_job(container_group_name: str, *, resource_group: str | None = None) -> None:
    rg = (resource_group or os.environ.get("ACI_RESOURCE_GROUP") or "").strip()
    if not rg:
        raise ValueError("ACI_RESOURCE_GROUP must be set.")
    client, _ = _aci_client()
    client.container_groups.begin_delete(rg, container_group_name, polling=False)


def aci_dispatcher_configured() -> bool:
    if not (_subscription_id_from_environ()):
        return False
    rg = os.environ.get("ACI_RESOURCE_GROUP", "").strip()
    image = os.environ.get("ACI_IMAGE", "").strip()
    if not rg or not image:
        return False
    if ".azurecr.io/" in image.lower():
        u = os.environ.get("ACI_REGISTRY_USERNAME", "").strip()
        p = os.environ.get("ACI_REGISTRY_PASSWORD", "").strip()
        return bool(u and p)
    return True
