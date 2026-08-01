from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from redra_mcp.database import connect, replace_records
from redra_mcp.models import (
    ATTRIBUTION,
    REDRA_ATTRIBUTION,
    REDRA_SOURCE_CHANGES,
    REDRA_SOURCE_DATASET_URL,
    REDRA_SOURCE_LICENSE,
    REDRA_SOURCE_NAME,
    SOURCE_LICENSE,
)
from redra_mcp.normalization import current_us_date, normalize_record, safe_url


PUBLICATION_SCHEMA = "redra-settlement-catalog/v1"
MAX_MANIFEST_BYTES = 1 * 1024 * 1024
MAX_DATASET_BYTES = 25 * 1024 * 1024
MAX_SETTLEMENTS = 50_000
TRUST_TIERS = {"A", "B"}
UPCOMING_STAGES = {
    "settlement_announced",
    "preliminary_approval_pending",
    "preliminarily_approved",
    "notice_or_portal_pending",
}


class DatasetImportError(RuntimeError):
    """Raised when a source payload cannot be imported safely."""


def validate_payload(payload: Any) -> dict[str, Any]:
    """Validate the legacy SettleSignal-compatible single-file feed."""
    if not isinstance(payload, dict):
        raise DatasetImportError("SettleSignal payload must be a JSON object")
    settlements = payload.get("settlements")
    if not isinstance(settlements, list):
        raise DatasetImportError("SettleSignal payload is missing settlements[]")
    if len(settlements) > MAX_SETTLEMENTS:
        raise DatasetImportError(
            f"dataset exceeds the {MAX_SETTLEMENTS:,}-record safety limit"
        )
    if not all(isinstance(record, dict) for record in settlements):
        raise DatasetImportError("every settlement must be a JSON object")
    declared_count = payload.get("count")
    if declared_count is not None and int(declared_count) != len(settlements):
        raise DatasetImportError(
            f"declared count {declared_count} does not match {len(settlements)} records"
        )
    return payload


def import_payload(payload: Any, database_path: Path) -> int:
    """Import a legacy single-file feed for backwards compatibility."""
    document = validate_payload(payload)
    today = current_us_date()
    records = [normalize_record(raw, today=today) for raw in document["settlements"]]
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise DatasetImportError("source payload contains duplicate settlement IDs")

    metadata = {
        "dataset_generated_at": document.get("generated"),
        "dataset_modified_at": document.get("dateModified"),
        "source_url": safe_url(
            document.get("source"), allowed_hosts={"settlesignal.com"}
        )
        or "https://settlesignal.com/data/settlements.json",
        "source_name": "SettleSignal",
        "source_license": SOURCE_LICENSE,
        "source_attribution": ATTRIBUTION,
        "independent_dataset": "false",
        "upcoming_record_count": 0,
    }
    connection = connect(database_path)
    try:
        return replace_records(connection, records, metadata)
    finally:
        connection.close()


def validate_publication_manifest(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != PUBLICATION_SCHEMA:
        raise DatasetImportError("publication manifest has an unsupported schema")
    if value.get("schema_version") != 1:
        raise DatasetImportError("publication manifest has an unsupported version")
    feeds = value.get("feeds")
    if not isinstance(feeds, dict) or set(feeds) != {"open", "upcoming"}:
        raise DatasetImportError("publication manifest must contain open and upcoming feeds")
    total = 0
    for feed in ("open", "upcoming"):
        item = feeds.get(feed)
        if not isinstance(item, dict):
            raise DatasetImportError(f"{feed} feed metadata is invalid")
        path = str(item.get("path") or "")
        digest = str(item.get("sha256") or "")
        count = item.get("count")
        size = item.get("bytes")
        if (
            not path.startswith("objects/")
            or ".." in path.split("/")
            or urlparse(path).scheme
        ):
            raise DatasetImportError(f"{feed} feed path is not a safe relative object")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise DatasetImportError(f"{feed} feed hash is invalid")
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= MAX_SETTLEMENTS:
            raise DatasetImportError(f"{feed} feed count is invalid")
        if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_DATASET_BYTES:
            raise DatasetImportError(f"{feed} feed byte size is invalid")
        total += count
    if value.get("open_count") != feeds["open"]["count"]:
        raise DatasetImportError("manifest open count differs from its feed")
    if value.get("upcoming_count") != feeds["upcoming"]["count"]:
        raise DatasetImportError("manifest upcoming count differs from its feed")
    if value.get("claimable_total_count") != feeds["open"]["count"]:
        raise DatasetImportError("manifest claimable count must equal the open feed")
    if value.get("record_count") != total:
        raise DatasetImportError("manifest record count differs from its feeds")
    if int(value.get("independent_lineage_unresolved") or 0) != 0:
        raise DatasetImportError("manifest contains unresolved discovery lineage")
    try:
        date.fromisoformat(str(value.get("dateModified") or ""))
    except ValueError as exc:
        raise DatasetImportError("manifest dateModified must be an ISO date") from exc
    return value


def validate_publication_feed(
    value: Any, *, feed: str, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    if not isinstance(value, dict) or value.get("schema") != PUBLICATION_SCHEMA:
        raise DatasetImportError(f"{feed} feed has an unsupported schema")
    if value.get("schema_version") != 1 or value.get("feed") != feed:
        raise DatasetImportError(f"{feed} feed identity is invalid")
    rows = value.get("settlements")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise DatasetImportError(f"{feed} feed settlements must be an object array")
    if len(rows) != manifest["feeds"][feed]["count"] or value.get("count") != len(rows):
        raise DatasetImportError(f"{feed} feed count differs from the manifest")
    if value.get("generated") != manifest.get("generated"):
        raise DatasetImportError(f"{feed} feed generation differs from the manifest")
    if value.get("dateModified") != manifest.get("dateModified"):
        raise DatasetImportError(f"{feed} feed date differs from the manifest")
    return rows


def _validate_publication_row(raw: dict[str, Any], *, feed: str, today: date) -> None:
    record_id = str(raw.get("id") or "")
    if not re.fullmatch(r"redra-[a-f0-9]{24}", record_id):
        raise DatasetImportError(f"invalid Redra record ID: {record_id!r}")
    if raw.get("provenance_tier") not in TRUST_TIERS or raw.get("independently_discovered") is not True:
        raise DatasetImportError(f"{record_id} lacks independent Tier A/B provenance")
    deadline_text = str(raw.get("claim_deadline") or "")
    if deadline_text:
        try:
            deadline = date.fromisoformat(deadline_text)
        except ValueError as exc:
            raise DatasetImportError(f"{record_id} has an invalid deadline") from exc
        if deadline < today:
            raise DatasetImportError(f"{record_id} has an expired deadline")
    if feed == "open":
        if (
            raw.get("normalized_status") != "open"
            or raw.get("claimability") != "claim_open"
            or raw.get("include_in_claimable_total") is not True
            or raw.get("claim_url_available") is not True
            or not safe_url(raw.get("official_claim_url"))
        ):
            raise DatasetImportError(f"{record_id} violates open publication invariants")
    elif (
        raw.get("normalized_status") != "upcoming"
        or raw.get("claimability") != "upcoming"
        or raw.get("include_in_claimable_total") is not False
        or raw.get("future_claim_window_evidenced") is not True
        or raw.get("official_claim_url") is not None
        or raw.get("lifecycle_stage") not in UPCOMING_STAGES
    ):
        raise DatasetImportError(f"{record_id} violates upcoming publication invariants")


def import_publication_bundle(
    manifest: Any,
    feed_documents: dict[str, Any],
    database_path: Path,
    *,
    manifest_url: str,
    manifest_sha256: str,
    max_open_drop_fraction: float = 0.15,
) -> int:
    document = validate_publication_manifest(manifest)
    today = current_us_date()
    records = []
    for feed in ("open", "upcoming"):
        rows = validate_publication_feed(
            feed_documents.get(feed), feed=feed, manifest=document
        )
        for raw in rows:
            _validate_publication_row(raw, feed=feed, today=today)
            record = normalize_record(raw, today=today)
            expected_status = "open" if feed == "open" else "upcoming"
            if record.normalized_status != expected_status:
                raise DatasetImportError(
                    f"{record.id} changed lifecycle state during normalization"
                )
            records.append(record)
    ids = [record.id for record in records]
    if len(ids) != len(set(ids)):
        raise DatasetImportError("publication feeds contain duplicate IDs")
    claim_urls = [record.official_claim_url for record in records if record.official_claim_url]
    if len(claim_urls) != len(set(claim_urls)):
        raise DatasetImportError("publication open feed contains duplicate claim URLs")

    connection = connect(database_path)
    try:
        prior_metadata = {
            row["key"]: row["value"]
            for row in connection.execute("SELECT key, value FROM metadata")
        }
        if prior_metadata.get("source_name") == REDRA_SOURCE_NAME:
            prior_open = connection.execute(
                "SELECT COUNT(*) FROM settlements WHERE normalized_status = 'open'"
            ).fetchone()[0]
            new_open = document["open_count"]
            if prior_open and new_open < prior_open * (1 - max_open_drop_fraction):
                raise DatasetImportError(
                    f"open count fell from {prior_open} to {new_open}, beyond the "
                    f"{max_open_drop_fraction:.0%} safety threshold"
                )
        metadata = {
            "dataset_generated_at": document.get("generated"),
            "dataset_modified_at": document.get("dateModified"),
            "source_url": manifest_url,
            "source_name": REDRA_SOURCE_NAME,
            "source_license": document.get("source_license") or REDRA_SOURCE_LICENSE,
            "source_attribution": document.get("attribution") or REDRA_ATTRIBUTION,
            "source_dataset_url": manifest_url or REDRA_SOURCE_DATASET_URL,
            "source_changes": REDRA_SOURCE_CHANGES,
            "upcoming_record_count": document["upcoming_count"],
            "independent_dataset": "true",
            "publication_manifest_sha256": manifest_sha256,
            "claimable_total_count": document["claimable_total_count"],
        }
        return replace_records(connection, records, metadata)
    finally:
        connection.close()


def _download(active_client: httpx.Client, url: str, *, maximum: int) -> bytes:
    with active_client.stream("GET", url) as response:
        response.raise_for_status()
        declared_size = response.headers.get("content-length")
        if declared_size and int(declared_size) > maximum:
            raise DatasetImportError(f"dataset object exceeds {maximum} bytes")
        content = bytearray()
        for chunk in response.iter_bytes():
            content.extend(chunk)
            if len(content) > maximum:
                raise DatasetImportError(f"dataset object exceeds {maximum} bytes")
    return bytes(content)


def _update_publication(
    database_path: Path,
    manifest_url: str,
    manifest_bytes: bytes,
    *,
    active_client: httpx.Client,
) -> int:
    manifest = validate_publication_manifest(json.loads(manifest_bytes))
    documents: dict[str, Any] = {}
    manifest_origin = urlparse(manifest_url).netloc
    for feed in ("open", "upcoming"):
        metadata = manifest["feeds"][feed]
        feed_url = urljoin(manifest_url, metadata["path"])
        if urlparse(feed_url).netloc != manifest_origin:
            raise DatasetImportError("publication feed escaped the manifest origin")
        content = _download(active_client, feed_url, maximum=MAX_DATASET_BYTES)
        if len(content) != metadata["bytes"]:
            raise DatasetImportError(f"{feed} feed byte size differs from manifest")
        if hashlib.sha256(content).hexdigest() != metadata["sha256"]:
            raise DatasetImportError(f"{feed} feed hash differs from manifest")
        documents[feed] = json.loads(content)
    return import_publication_bundle(
        manifest,
        documents,
        database_path,
        manifest_url=manifest_url,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def update_dataset(
    database_path: Path,
    source_url: str,
    *,
    timeout: float = 20,
    client: httpx.Client | None = None,
) -> int:
    owns_client = client is None
    active_client = client or httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "redra-mcp/0.1 (+https://redra.ai)"},
    )
    try:
        content = _download(active_client, source_url, maximum=MAX_DATASET_BYTES)
        payload = json.loads(content)
        if isinstance(payload, dict) and payload.get("schema") == PUBLICATION_SCHEMA:
            if len(content) > MAX_MANIFEST_BYTES:
                raise DatasetImportError("publication manifest exceeds the 1 MiB limit")
            return _update_publication(
                database_path,
                source_url,
                content,
                active_client=active_client,
            )
        return import_payload(payload, database_path)
    except (httpx.HTTPError, ValueError, TypeError, sqlite3.Error) as exc:
        if isinstance(exc, DatasetImportError):
            raise
        raise DatasetImportError(f"unable to download settlement dataset: {exc}") from exc
    finally:
        if owns_client:
            active_client.close()
