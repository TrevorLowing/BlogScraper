from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings

UTC = timezone.utc


@dataclass
class PostMetadata:
    canonical_url: str
    post_id: str
    published_date: str | None
    fetched_at_utc: str
    content_sha256: str
    source_language: str
    content_selector_used: str | None
    translator_mode: str
    crawl_run_id: str


def _service(connection_string: str) -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(connection_string)


def ensure_container(connection_string: str, container_name: str) -> None:
    cc = _service(connection_string).get_container_client(container_name)
    try:
        cc.create_container()
    except ResourceExistsError:
        pass


def list_existing_post_ids(connection_string: str, container_name: str) -> set[str]:
    ensure_container(connection_string, container_name)
    ids: set[str] = set()
    cc = _service(connection_string).get_container_client(container_name)
    for blob in cc.list_blobs(name_starts_with="posts/"):
        parts = blob.name.split("/")
        if len(parts) == 3 and parts[2] == "metadata.json":
            ids.add(parts[1])
    return ids


def metadata_blob_path(post_id: str) -> str:
    return f"posts/{post_id}/metadata.json"


def post_has_metadata(connection_string: str, container_name: str, post_id: str) -> bool:
    cc = _service(connection_string).get_container_client(container_name)
    return cc.get_blob_client(metadata_blob_path(post_id)).exists()


def upload_post_artifacts(
    connection_string: str,
    container_name: str,
    *,
    post_id: str,
    raw_html: str,
    zh_fragment: str,
    en_translation: str,
    metadata: PostMetadata,
    dry_run: bool,
) -> None:
    if dry_run:
        return

    ensure_container(connection_string, container_name)
    cc = _service(connection_string).get_container_client(container_name)

    payloads: tuple[tuple[str, str, str], ...] = (
        (f"posts/{post_id}/raw.html", raw_html, "text/html; charset=utf-8"),
        (f"posts/{post_id}/content_zh.html", zh_fragment, "text/html; charset=utf-8"),
        (f"posts/{post_id}/content_en.html", en_translation, "text/html; charset=utf-8"),
        (
            f"posts/{post_id}/metadata.json",
            json.dumps(asdict(metadata), ensure_ascii=False, indent=2),
            "application/json; charset=utf-8",
        ),
    )
    for path, payload, ctype in payloads:
        cc.upload_blob(
            path,
            payload.encode("utf-8"),
            overwrite=True,
            content_settings=ContentSettings(content_type=ctype),
        )


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).isoformat()
