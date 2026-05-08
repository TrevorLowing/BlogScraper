"""ACI dispatcher env mapping — no Azure SDK calls."""

from blog_scraper.aci_invoke import aci_dispatcher_configured, build_aci_environment_variables
from blog_scraper.pipeline import PipelineOptions


def test_aci_dispatcher_requires_acr_creds(monkeypatch) -> None:
    monkeypatch.setenv("ACI_SUBSCRIPTION_ID", "11111111-1111-1111-1111-111111111111")
    monkeypatch.setenv("ACI_RESOURCE_GROUP", "rg-test")
    monkeypatch.delenv("ACI_REGISTRY_USERNAME", raising=False)
    monkeypatch.delenv("ACI_REGISTRY_PASSWORD", raising=False)
    monkeypatch.setenv(
        "ACI_IMAGE",
        "myacr.azurecr.io/blog-scraper-runner:v1",
    )
    assert aci_dispatcher_configured() is False

    monkeypatch.setenv("ACI_REGISTRY_USERNAME", "myacr")
    monkeypatch.setenv("ACI_REGISTRY_PASSWORD", "x")
    assert aci_dispatcher_configured() is True


def test_blogs_storage_forwarded_secure(monkeypatch) -> None:
    monkeypatch.delenv("BLOG_SCRAPER_STORAGE", raising=False)
    monkeypatch.setenv("AzureWebJobsStorage", "fake;AccountKey=Y;fake")
    opts = PipelineOptions(dry_run=True)
    vars_ = build_aci_environment_variables(opts)
    azure = next((v for v in vars_ if v.name == "AzureWebJobsStorage"), None)
    assert azure is not None
    assert azure.secure_value is not None
    assert getattr(azure, "value", None) is None
