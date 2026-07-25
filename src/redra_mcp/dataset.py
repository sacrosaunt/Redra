from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from redra_mcp.database import connect, replace_records
from redra_mcp.models import ATTRIBUTION, SOURCE_LICENSE
from redra_mcp.normalization import current_us_date, normalize_record, safe_url


MAX_DATASET_BYTES = 25 * 1024 * 1024
MAX_SETTLEMENTS = 50_000


class DatasetImportError(RuntimeError):
    """Raised when a source payload cannot be imported safely."""


def validate_payload(payload: Any) -> dict[str, Any]:
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
    }
    connection = connect(database_path)
    try:
        return replace_records(connection, records, metadata)
    finally:
        connection.close()


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
        headers={"User-Agent": "redra-mcp/0.1 (+https://github.com/)"},
    )
    try:
        with active_client.stream("GET", source_url) as response:
            response.raise_for_status()
            declared_size = response.headers.get("content-length")
            if declared_size and int(declared_size) > MAX_DATASET_BYTES:
                raise DatasetImportError("dataset exceeds the 25 MiB safety limit")
            content = bytearray()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_DATASET_BYTES:
                    raise DatasetImportError("dataset exceeds the 25 MiB safety limit")
        return import_payload(json.loads(content), database_path)
    except (httpx.HTTPError, ValueError) as exc:
        raise DatasetImportError(f"unable to download SettleSignal dataset: {exc}") from exc
    finally:
        if owns_client:
            active_client.close()
