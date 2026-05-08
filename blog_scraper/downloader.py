from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from azure.storage.blob import BlobServiceClient


@dataclass(frozen=True)
class RecentPost:
    """Minimal blob-index row used to pick and order "latest" posts."""
    post_id: str
    metadata_blob: str
    last_modified: datetime


def _service(connection_string: str) -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(connection_string)


def _post_id_from_metadata_blob(blob_name: str) -> str | None:
    parts = blob_name.split("/")
    if len(parts) == 3 and parts[0] == "posts" and parts[2] == "metadata.json":
        return parts[1]
    return None


def list_recent_posts(
    connection_string: str,
    container_name: str,
    limit: int = 10,
) -> list[RecentPost]:
    """
    Return newest posts by metadata blob modification time.

    Important: this ranks by when `metadata.json` was last written in blob,
    not by article publish date.
    """
    cc = _service(connection_string).get_container_client(container_name)
    rows: list[RecentPost] = []
    for blob in cc.list_blobs(name_starts_with="posts/"):
        post_id = _post_id_from_metadata_blob(blob.name)
        if not post_id:
            continue
        rows.append(
            RecentPost(
                post_id=post_id,
                metadata_blob=blob.name,
                last_modified=blob.last_modified,
            )
        )
    rows.sort(key=lambda r: r.last_modified, reverse=True)
    return rows[: max(0, int(limit))]


def _download_text(cc, path: str) -> str:
    return cc.get_blob_client(path).download_blob().readall().decode("utf-8")


def _safe_token(v: str) -> str:
    out = []
    for ch in v:
        if ch.isalnum() or ch in ("-", "_"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def _date_token(meta: dict) -> str:
    """Pick stable folder prefix token: published_date -> fetched date -> fallback."""
    pd = meta.get("published_date")
    if isinstance(pd, str) and pd.strip():
        return _safe_token(pd.strip())
    fetched = meta.get("fetched_at_utc")
    if isinstance(fetched, str) and len(fetched) >= 10:
        return _safe_token(fetched[:10])
    return "unknown-date"


def download_recent_posts(
    connection_string: str,
    container_name: str,
    output_dir: str | Path,
    *,
    limit: int = 10,
    include_raw_html: bool = False,
) -> dict:
    """
    Download latest N posts from blob storage into a local review folder.

    Output shape:
    - one folder per post (`<date>_<post_id>`)
    - zh/en HTML + metadata files
    - optional raw HTML
    - top-level `index.json` summary for easy scripting
    """
    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    cc = _service(connection_string).get_container_client(container_name)
    # "Recent" is based on metadata blob write time, then truncated to `limit`.
    recent = list_recent_posts(connection_string, container_name, limit=limit)

    exported: list[dict] = []
    for row in recent:
        metadata_text = _download_text(cc, f"posts/{row.post_id}/metadata.json")
        meta = json.loads(metadata_text)
        date_tok = _date_token(meta)
        base = f"{date_tok}_{row.post_id}"

        post_dir = out_root / base
        post_dir.mkdir(parents=True, exist_ok=True)

        zh_text = _download_text(cc, f"posts/{row.post_id}/content_zh.html")
        en_text = _download_text(cc, f"posts/{row.post_id}/content_en.html")

        metadata_file = post_dir / f"{base}_metadata.json"
        zh_file = post_dir / f"{base}_content_zh.html"
        en_file = post_dir / f"{base}_content_en.html"

        metadata_file.write_text(metadata_text, encoding="utf-8")
        zh_file.write_text(zh_text, encoding="utf-8")
        en_file.write_text(en_text, encoding="utf-8")

        raw_path = None
        if include_raw_html:
            raw_text = _download_text(cc, f"posts/{row.post_id}/raw.html")
            raw_path = post_dir / f"{base}_raw.html"
            raw_path.write_text(raw_text, encoding="utf-8")

        exported.append(
            {
                "post_id": row.post_id,
                "published_date": meta.get("published_date"),
                "canonical_url": meta.get("canonical_url"),
                "target_dir": str(post_dir),
                "content_zh_file": str(zh_file),
                "content_en_file": str(en_file),
                "metadata_file": str(metadata_file),
                "raw_html": str(raw_path) if raw_path else None,
                "last_modified_utc": row.last_modified.isoformat(),
            }
        )

    summary = {
        "container_name": container_name,
        "output_dir": str(out_root),
        "limit": limit,
        "downloaded_count": len(exported),
        "posts": exported,
    }
    (out_root / "index.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary
