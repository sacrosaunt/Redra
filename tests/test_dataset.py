from __future__ import annotations

import copy

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
            SearchQuery(keywords=["Acme", "wages"], status="all")
        )
        assert and_miss.count == 0

        breach_type = provider.search(
            SearchQuery(status="all", settlement_type="data_breach_settlement")
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

        closed_ca = provider.search(SearchQuery(state="CA", status="closed"))
        assert closed_ca.count == 1

        info = provider.info()
        assert info.record_count == 2
        assert info.open_record_count == 1
        assert info.schema_version == 2
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
        with pytest.raises(DatasetImportError, match="25 MiB safety limit"):
            update_dataset(
                tmp_path / "settlements.db",
                "https://settlesignal.com/data/settlements.json",
                client=client,
            )
    finally:
        client.close()
