from __future__ import annotations

from unittest.mock import MagicMock

from redra_mcp.models import ATTRIBUTION, DISCLAIMER, SearchQuery, SearchResponse
from redra_mcp.service import RedraService


def response(query: SearchQuery) -> SearchResponse:
    return SearchResponse(
        query=query,
        count=0,
        items=[],
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
