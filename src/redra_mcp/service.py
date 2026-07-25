from __future__ import annotations

from datetime import date

from redra_mcp.models import ProofRequirement, SearchQuery
from redra_mcp.providers.base import SettlementProvider


class RedraService:
    def __init__(self, provider: SettlementProvider):
        self.provider = provider

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
        return self.provider.search(query).model_dump(mode="json")

    def get(self, settlement_id: str) -> dict:
        record = self.provider.get(settlement_id)
        if record is None:
            raise ValueError(f"settlement not found: {settlement_id}")
        return record.model_dump(mode="json")

    def info(self) -> dict:
        return self.provider.info().model_dump(mode="json")

    def close(self) -> None:
        self.provider.close()
