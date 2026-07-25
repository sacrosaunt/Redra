from __future__ import annotations

from typing import Protocol

from redra_mcp.models import DatasetInfo, SearchQuery, SearchResponse, SettlementRecord


class ProviderError(RuntimeError):
    """A data provider could not complete a request."""


class SettlementProvider(Protocol):
    def search(self, query: SearchQuery) -> SearchResponse: ...

    def get(self, settlement_id: str) -> SettlementRecord | None: ...

    def info(self) -> DatasetInfo: ...

    def close(self) -> None: ...
