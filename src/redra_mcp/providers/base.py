from __future__ import annotations

from typing import Protocol

from redra_mcp.models import DatasetInfo, SearchQuery, SearchResponse, SettlementRecord


class ProviderError(RuntimeError):
    """A data provider could not complete a request."""


class SettlementProvider(Protocol):
    def search(self, query: SearchQuery) -> SearchResponse:
        ...

    def search_many(self, queries: list[SearchQuery]) -> list[SearchResponse]:
        ...

    def get(self, settlement_id: str) -> SettlementRecord | None:
        ...

    def get_many(
        self, settlement_ids: list[str]
    ) -> tuple[list[SettlementRecord], list[str]]:
        ...

    def info(self) -> DatasetInfo:
        ...

    def close(self) -> None:
        ...
