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

from redra_mcp.models import ProofRequirement, SearchQuery, SearchResponse
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
                    update={"query": SearchQuery(keywords=[], status=None)}
                ),
            )
            while len(self._search_cache) > self.search_cache_max_entries:
                self._search_cache.popitem(last=False)

    def search(
        self,
        *,
        keywords: list[str] | None = None,
        state: str | None = None,
        status: str | None = "open",
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

    def get(self, settlement_id: str) -> dict:
        record = self.provider.get(settlement_id)
        if record is None:
            raise ValueError(f"settlement not found: {settlement_id}")
        return record.model_dump(mode="json")

    def info(self) -> dict:
        return self.provider.info().model_dump(mode="json")

    def close(self) -> None:
        self.provider.close()
