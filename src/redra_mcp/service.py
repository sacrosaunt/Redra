from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from threading import Lock

from redra_mcp.models import (
    ProofRequirement,
    SearchQuery,
    SearchResponse,
    SearchStatus,
)
from redra_mcp.providers.base import SettlementProvider


@dataclass(slots=True)
class SearchCacheEntry:
    expires_at: float
    response: SearchResponse


class RedraService:
    def __init__(
        self,
        provider: SettlementProvider,
        *,
        search_cache_ttl_seconds: float = 30,
        search_cache_max_entries: int = 512,
        clock: Callable[[], float] = time.monotonic,
        cache_key_secret: bytes | None = None,
    ):
        self.provider = provider
        self.search_cache_ttl_seconds = max(0.0, search_cache_ttl_seconds)
        self.search_cache_max_entries = max(0, search_cache_max_entries)
        self._clock = clock
        self._cache_key_secret = cache_key_secret or secrets.token_bytes(32)
        self._search_cache: OrderedDict[str, SearchCacheEntry] = OrderedDict()
        self._search_cache_lock = Lock()

    def _search_cache_key(self, query: SearchQuery) -> str:
        normalized = (
            tuple(sorted(keyword.casefold() for keyword in query.keywords)),
            query.state,
            query.status,
            query.settlement_type,
            query.proof_required,
            query.deadline_after.isoformat() if query.deadline_after else None,
            query.deadline_before.isoformat() if query.deadline_before else None,
            query.limit,
        )
        encoded = json.dumps(normalized, separators=(",", ":")).encode()
        return hmac.new(
            self._cache_key_secret,
            encoded,
            hashlib.sha256,
        ).hexdigest()

    def _cached_search(self, query: SearchQuery) -> SearchResponse | None:
        if not self.search_cache_ttl_seconds or not self.search_cache_max_entries:
            return None
        key = self._search_cache_key(query)
        now = self._clock()
        with self._search_cache_lock:
            entry = self._search_cache.pop(key, None)
            if entry is None:
                return None
            if entry.expires_at <= now:
                return None
            self._search_cache[key] = entry
            return entry.response.model_copy(update={"query": query})

    def _store_search(self, query: SearchQuery, response: SearchResponse) -> None:
        if not self.search_cache_ttl_seconds or not self.search_cache_max_entries:
            return
        key = self._search_cache_key(query)
        with self._search_cache_lock:
            self._search_cache.pop(key, None)
            self._search_cache[key] = SearchCacheEntry(
                expires_at=self._clock() + self.search_cache_ttl_seconds,
                response=response.model_copy(
                    update={"query": SearchQuery(keywords=[], status=query.status)}
                ),
            )
            while len(self._search_cache) > self.search_cache_max_entries:
                self._search_cache.popitem(last=False)

    def search(
        self,
        *,
        keywords: list[str] | None = None,
        state: str | None = None,
        status: SearchStatus = "open",
        settlement_type: str | None = None,
        proof_required: ProofRequirement | None = None,
        deadline_after: date | None = None,
        deadline_before: date | None = None,
        limit: int = 20,
    ) -> dict:
        query = SearchQuery(
            keywords=keywords or [],
            state=state,
            status=status,
            settlement_type=settlement_type,
            proof_required=proof_required,
            deadline_after=deadline_after,
            deadline_before=deadline_before,
            limit=limit,
        )
        response = self._cached_search(query)
        if response is None:
            response = self.provider.search(query)
            self._store_search(query, response)
        return response.model_dump(mode="json")

    def search_many(
        self, queries: list[SearchQuery], *, max_total_results: int = 50
    ) -> dict:
        if not 1 <= max_total_results <= 100:
            raise ValueError("max_total_results must be between 1 and 100")
        responses: list[SearchResponse | None] = [None] * len(queries)
        pending: dict[str, tuple[SearchQuery, list[int]]] = {}
        for index, query in enumerate(queries):
            cached = self._cached_search(query)
            if cached is not None:
                responses[index] = cached
                continue
            key = self._search_cache_key(query)
            if key in pending:
                pending[key][1].append(index)
            else:
                pending[key] = (query, [index])

        if pending:
            unique_queries = [entry[0] for entry in pending.values()]
            provider_search_many = getattr(self.provider, "search_many", None)
            if callable(provider_search_many):
                fresh = provider_search_many(unique_queries)
            else:
                fresh = [self.provider.search(query) for query in unique_queries]
            if len(fresh) != len(unique_queries):
                raise RuntimeError("provider returned an invalid batch search response")
            for (query, indices), response in zip(pending.values(), fresh, strict=True):
                self._store_search(query, response)
                for index in indices:
                    responses[index] = response.model_copy(
                        update={"query": queries[index]}
                    )

        resolved = [response for response in responses if response is not None]
        if len(resolved) != len(queries):
            raise RuntimeError("provider did not resolve every batch search query")
        first = resolved[0]
        records_by_id: dict[str, dict] = {}
        matched_query_indices: dict[str, list[int]] = {}
        sampled_ids_by_query: list[list[str]] = []
        for query_index, response in enumerate(resolved):
            sampled_ids: list[str] = []
            for item in response.items:
                sampled_ids.append(item.id)
                if item.id not in records_by_id:
                    records_by_id[item.id] = item.model_dump(mode="json")
                    matched_query_indices[item.id] = []
                if query_index not in matched_query_indices[item.id]:
                    matched_query_indices[item.id].append(query_index)
            sampled_ids_by_query.append(sampled_ids)

        unique_ids = list(records_by_id)
        selected_ids = unique_ids[:max_total_results]
        selected_id_set = set(selected_ids)
        return {
            "query_count": len(queries),
            "executed_query_count": len(queries),
            "queries": [
                {
                    "query_index": query_index,
                    "query": response.query.model_dump(mode="json"),
                    "count": response.count,
                    "sampled_count": len(sampled_ids_by_query[query_index]),
                    "returned_item_ids": [
                        settlement_id
                        for settlement_id in sampled_ids_by_query[query_index]
                        if settlement_id in selected_id_set
                    ],
                    "omitted_sampled_count": sum(
                        settlement_id not in selected_id_set
                        for settlement_id in sampled_ids_by_query[query_index]
                    ),
                }
                for query_index, response in enumerate(resolved)
            ],
            "unique_sampled_item_count": len(unique_ids),
            "returned_item_count": len(selected_ids),
            "omitted_unique_item_count": len(unique_ids) - len(selected_ids),
            "max_total_results": max_total_results,
            "truncated": len(unique_ids) > len(selected_ids),
            "items": [
                {
                    **records_by_id[settlement_id],
                    "matched_query_indices": matched_query_indices[settlement_id],
                }
                for settlement_id in selected_ids
            ],
            "provider": first.provider,
            "attribution": first.attribution,
            "disclaimer": first.disclaimer,
        }

    def get(self, settlement_id: str) -> dict:
        record = self.provider.get(settlement_id)
        if record is None:
            raise ValueError(f"settlement not found: {settlement_id}")
        return record.model_dump(mode="json")

    def get_many(self, settlement_ids: list[str]) -> dict:
        normalized_ids: list[str] = []
        seen: set[str] = set()
        for settlement_id in settlement_ids:
            normalized = settlement_id.strip().rstrip("/").rsplit("/", 1)[-1]
            if normalized and normalized not in seen:
                normalized_ids.append(normalized)
                seen.add(normalized)

        provider_get_many = getattr(self.provider, "get_many", None)
        if not normalized_ids:
            records = []
            not_found = []
        elif callable(provider_get_many):
            records, not_found = provider_get_many(normalized_ids)
        else:
            records = []
            not_found = []
            for settlement_id in normalized_ids:
                record = self.provider.get(settlement_id)
                if record is None:
                    not_found.append(settlement_id)
                else:
                    records.append(record)
        return {
            "requested_count": len(normalized_ids),
            "found_count": len(records),
            "items": [record.model_dump(mode="json") for record in records],
            "not_found": not_found,
        }

    def info(self) -> dict:
        return self.provider.info().model_dump(mode="json")

    def close(self) -> None:
        self.provider.close()
