from __future__ import annotations

from unittest.mock import MagicMock

from redra_mcp.models import (
    ATTRIBUTION,
    DISCLAIMER,
    SearchQuery,
    SearchResponse,
    SettlementRecord,
)
from redra_mcp.service import RedraService


def record(settlement_id: str) -> SettlementRecord:
    return SettlementRecord(
        id=settlement_id,
        title=settlement_id.replace("-", " ").title(),
        status="Open for claims",
        normalized_status="open",
        source_url=f"https://example.test/{settlement_id}",
    )


def response(
    query: SearchQuery, items: list[SettlementRecord] | None = None
) -> SearchResponse:
    return SearchResponse(
        query=query,
        count=len(items or []),
        items=items or [],
        provider="test",
        attribution=ATTRIBUTION,
        disclaimer=DISCLAIMER,
    )


def test_search_cache_reuses_semantically_identical_queries():
    now = [100.0]
    provider = MagicMock()
    provider.search.side_effect = lambda query: response(query)
    service = RedraService(
        provider,
        search_cache_ttl_seconds=30,
        search_cache_max_entries=2,
        clock=lambda: now[0],
    )

    first = service.search(keywords=["Acme", "Breach"], state="ca")
    second = service.search(keywords=["breach", "acme"], state="CA")

    assert provider.search.call_count == 1
    assert first["query"]["keywords"] == ["Acme", "Breach"]
    assert second["query"]["keywords"] == ["breach", "acme"]
    cache_key, cache_entry = next(iter(service._search_cache.items()))
    assert "acme" not in cache_key.casefold()
    assert cache_entry.response.query.keywords == []

    now[0] += 31
    service.search(keywords=["Acme", "Breach"], state="CA")
    assert provider.search.call_count == 2


def test_search_cache_can_be_disabled():
    provider = MagicMock()
    provider.search.side_effect = lambda query: response(query)
    service = RedraService(provider, search_cache_ttl_seconds=0)

    service.search(keywords=["Acme"])
    service.search(keywords=["Acme"])

    assert provider.search.call_count == 2


def test_batch_search_groups_queries_and_reuses_cache_and_duplicates():
    provider = MagicMock()
    provider.search_many.side_effect = lambda queries: [
        response(query) for query in queries
    ]
    service = RedraService(provider, search_cache_ttl_seconds=30)

    first = service.search_many(
        [
            SearchQuery(keywords=["Fidelity"]),
            SearchQuery(keywords=["Amazon"]),
            SearchQuery(keywords=["fidelity"]),
        ]
    )
    second = service.search_many([SearchQuery(keywords=["Amazon"])])

    assert first["query_count"] == 3
    assert [result["query"]["keywords"] for result in first["queries"]] == [
        ["Fidelity"],
        ["Amazon"],
        ["fidelity"],
    ]
    assert provider.search_many.call_count == 1
    assert len(provider.search_many.call_args.args[0]) == 2
    assert second["queries"][0]["query"]["keywords"] == ["Amazon"]


def test_batch_search_deduplicates_records_and_maps_matching_queries():
    provider = MagicMock()
    shared = record("shared")
    only_first = record("only-first")
    only_second = record("only-second")
    provider.search_many.side_effect = lambda queries: [
        response(queries[0], [shared, only_first]),
        response(queries[1], [shared, only_second]),
    ]
    service = RedraService(provider, search_cache_ttl_seconds=0)

    result = service.search_many(
        [SearchQuery(keywords=["Alpha"]), SearchQuery(keywords=["Beta"])],
        max_total_results=2,
    )

    assert result["query_count"] == 2
    assert result["unique_sampled_item_count"] == 3
    assert result["returned_item_count"] == 2
    assert result["omitted_unique_item_count"] == 1
    assert result["max_total_results"] == 2
    assert result["truncated"] is True
    assert [item["id"] for item in result["items"]] == ["shared", "only-first"]
    assert result["items"][0]["matched_query_indices"] == [0, 1]
    assert result["queries"][0]["returned_item_ids"] == ["shared", "only-first"]
    assert result["queries"][0]["omitted_sampled_count"] == 0
    assert result["queries"][1]["returned_item_ids"] == ["shared"]
    assert result["queries"][1]["omitted_sampled_count"] == 1


def test_batch_search_rejects_invalid_total_result_cap():
    service = RedraService(MagicMock())

    for value in (0, 101):
        try:
            service.search_many(
                [SearchQuery(keywords=["Acme"])], max_total_results=value
            )
        except ValueError as error:
            assert "between 1 and 100" in str(error)
        else:
            raise AssertionError("invalid max_total_results was accepted")


def test_get_many_preserves_order_deduplicates_and_reports_missing():
    provider = MagicMock()
    provider.get_many.return_value = ([], ["missing", "other"])
    service = RedraService(provider)

    result = service.get_many(["missing", "https://example.test/other", "missing"])

    provider.get_many.assert_called_once_with(["missing", "other"])
    assert result == {
        "requested_count": 2,
        "found_count": 0,
        "items": [],
        "not_found": ["missing", "other"],
    }
