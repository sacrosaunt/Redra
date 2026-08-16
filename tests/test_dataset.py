from __future__ import annotations

import copy
import hashlib
import json

import httpx
import pytest

import redra_mcp.dataset as dataset_module
from redra_mcp.dataset import DatasetImportError, import_payload, update_dataset
from redra_mcp.models import SearchQuery
from redra_mcp.providers.sqlite import SQLiteProvider


def test_import_and_search(tmp_path, settlesignal_payload):
    database = tmp_path / "settlements.db"
    assert import_payload(settlesignal_payload, database) == 2

    provider = SQLiteProvider(database)
    try:
        response = provider.search(SearchQuery(keywords=["Acme"], status="open"))
        assert response.count == 1
        assert response.items[0].id == "acme-data-breach"
        assert response.items[0].source_license == "CC BY 4.0"
        assert response.items[0].source_license_url == (
            "https://creativecommons.org/licenses/by/4.0/"
        )
        assert "Data adapted from SettleSignal" in response.attribution
        assert "adds derived lifecycle" in response.items[0].source_changes

        and_match = provider.search(
            SearchQuery(keywords=["Acme", "data breach"], status="open")
        )
        assert and_match.count == 1
        and_miss = provider.search(
            SearchQuery(keywords=["Acme", "wages"], status="open")
        )
        assert and_miss.count == 0

        breach_type = provider.search(
            SearchQuery(status="open", settlement_type="data_breach_settlement")
        )
        assert breach_type.count == 1
        assert breach_type.items[0].id == "acme-data-breach"
        assert (
            breach_type.items[0].source_verification_status
            == "official_source_found"
        )
        assert breach_type.items[0].source_kind == "administrator"
        assert breach_type.items[0].claimability == "claim_open"
        assert breach_type.items[0].claim_url_available is True
        assert breach_type.items[0].quality_flags == []

        nationwide = provider.search(SearchQuery(state="NY", status="open"))
        assert nationwide.count == 1

        upcoming = provider.search(SearchQuery(status="upcoming"))
        assert upcoming.count == 0

        info = provider.info()
        assert info.record_count == 2
        assert info.open_record_count == 1
        assert info.upcoming_record_count == 0
        assert info.schema_version == 3
        assert info.source_dataset_url == (
            "https://huggingface.co/datasets/katana957/us-settlement-catalog"
        )
    finally:
        provider.close()


def test_rejects_declared_count_mismatch(tmp_path, settlesignal_payload):
    payload = copy.deepcopy(settlesignal_payload)
    payload["count"] = 3
    with pytest.raises(DatasetImportError, match="declared count"):
        import_payload(payload, tmp_path / "settlements.db")


def test_rejects_duplicate_ids(tmp_path, settlesignal_payload):
    payload = copy.deepcopy(settlesignal_payload)
    payload["settlements"][1]["url"] = payload["settlements"][0]["url"]
    with pytest.raises(DatasetImportError, match="duplicate"):
        import_payload(payload, tmp_path / "settlements.db")


def test_streaming_download_enforces_size_limit(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(dataset_module, "MAX_DATASET_BYTES", 32)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"x" * 33)
        )
    )
    try:
        with pytest.raises(DatasetImportError, match="exceeds 32 bytes"):
            update_dataset(
                tmp_path / "settlements.db",
                "https://settlesignal.com/data/settlements.json",
                client=client,
            )
    finally:
        client.close()


def _json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _publication_bundle():
    common = {
        "category": "Data Breach Settlement",
        "settlement_type": "data_breach_settlement",
        "proof_required": "unknown",
        "applicable_states": [],
        "expected_individual_payout": "$1,000",
        "maximum_cumulative_payout_cents": 100_000,
        "source_checked_at": "2026-08-01",
        "source_kind": "administrator",
        "source_verification_status": "administrator_verified",
        "quality_flags": [],
        "provenance_tier": "A",
        "independently_discovered": True,
        "source_name": "Redra",
        "source_license": "CC-BY-4.0",
    }
    open_row = {
        **common,
        "id": "redra-111111111111111111111111",
        "title": "Acme Account Incident Settlement",
        "description": "Acme account holders may submit a claim.",
        "eligibility": "People whose Acme account was affected.",
        "status": "Open for claims",
        "normalized_status": "open",
        "claimability": "claim_open",
        "lifecycle_stage": None,
        "claim_deadline": "2026-09-01",
        "official_claim_url": "https://claims.example/acme/file",
        "official_settlement_url": "https://claims.example/acme",
        "claim_url_available": True,
        "include_in_claimable_total": True,
        "future_claim_window_evidenced": False,
        "source_url": "https://claims.example/acme",
    }
    upcoming_row = {
        **common,
        "id": "redra-222222222222222222222222",
        "title": "FutureCo Preliminary Settlement",
        "description": "The court preliminarily approved a future claim process.",
        "eligibility": "FutureCo customers in the proposed class.",
        "status": "Upcoming",
        "normalized_status": "upcoming",
        "claimability": "upcoming",
        "lifecycle_stage": "preliminarily_approved",
        "claim_deadline": None,
        "official_claim_url": None,
        "official_settlement_url": "https://settlements.example/futureco",
        "claim_url_available": False,
        "include_in_claimable_total": False,
        "future_claim_window_evidenced": True,
        "source_url": "https://settlements.example/futureco",
    }
    generated = "2026-08-01T20:00:00+00:00"
    feeds = {}
    documents = {}
    for name, rows in (("open", [open_row]), ("upcoming", [upcoming_row])):
        document = {
            "schema": "redra-settlement-catalog/v1",
            "schema_version": 1,
            "feed": name,
            "generated": generated,
            "dateModified": "2026-08-01",
            "count": len(rows),
            "source": "https://redra.ai",
            "source_name": "Redra",
            "source_license": "CC-BY-4.0",
            "attribution": "Independent Redra sources.",
            "settlements": rows,
        }
        content = _json_bytes(document)
        digest = hashlib.sha256(content).hexdigest()
        path = f"objects/{name}-{digest}.json"
        feeds[name] = {
            "path": path,
            "sha256": digest,
            "bytes": len(content),
            "count": len(rows),
        }
        documents[path] = content
    manifest = {
        "schema": "redra-settlement-catalog/v1",
        "schema_version": 1,
        "generated": generated,
        "dateModified": "2026-08-01",
        "record_count": 2,
        "open_count": 1,
        "upcoming_count": 1,
        "claimable_total_count": 1,
        "independent_lineage_unresolved": 0,
        "feeds": feeds,
        "source": "https://redra.ai",
        "source_name": "Redra",
        "source_license": "CC-BY-4.0",
        "attribution": "Independent Redra sources.",
    }
    return manifest, documents


def test_imports_content_addressed_publication_and_separates_upcoming(tmp_path):
    manifest, objects = _publication_bundle()
    manifest_bytes = _json_bytes(manifest)

    def response(request):
        if request.url.path.endswith("/manifest.json"):
            return httpx.Response(200, content=manifest_bytes)
        path = request.url.path.split("/catalog/v1/", 1)[-1]
        return httpx.Response(200, content=objects[path])

    database = tmp_path / "settlements.db"
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        assert update_dataset(
            database,
            "https://data.redra.ai/catalog/v1/manifest.json",
            client=client,
        ) == 2

    provider = SQLiteProvider(database)
    try:
        open_results = provider.search(
            SearchQuery(keywords=["account holders"], status="open")
        )
        assert open_results.count == 1
        assert open_results.items[0].include_in_claimable_total is True
        assert open_results.items[0].source_name == "Redra"
        assert "independently collects" in open_results.items[0].source_changes

        upcoming = provider.search(
            SearchQuery(keywords=["proposed class"], status="upcoming")
        )
        assert upcoming.count == 1
        assert upcoming.items[0].official_claim_url is None
        assert upcoming.items[0].future_claim_window_evidenced is True
        assert upcoming.items[0].include_in_claimable_total is False

        info = provider.info()
        assert info.record_count == 2
        assert info.open_record_count == 1
        assert info.upcoming_record_count == 1
        assert info.extra["claimable_total_count"] == 1
        assert info.extra["independent_dataset"] is True
        assert info.extra["publication_manifest_sha256"] == hashlib.sha256(
            manifest_bytes
        ).hexdigest()
    finally:
        provider.close()


def test_publication_hash_failure_preserves_existing_database(
    tmp_path, settlesignal_payload
):
    database = tmp_path / "settlements.db"
    import_payload(settlesignal_payload, database)
    manifest, objects = _publication_bundle()
    manifest["feeds"]["open"]["sha256"] = "0" * 64
    manifest_bytes = _json_bytes(manifest)

    def response(request):
        if request.url.path.endswith("/manifest.json"):
            return httpx.Response(200, content=manifest_bytes)
        path = request.url.path.split("/catalog/v1/", 1)[-1]
        return httpx.Response(200, content=objects[path])

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        with pytest.raises(DatasetImportError, match="hash differs"):
            update_dataset(
                database,
                "https://data.redra.ai/catalog/v1/manifest.json",
                client=client,
            )

    provider = SQLiteProvider(database)
    try:
        assert provider.info().record_count == 2
        assert provider.get("acme-data-breach") is not None
    finally:
        provider.close()
