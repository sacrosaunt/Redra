from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

from redra_mcp.database import SCHEMA_VERSION, connect
from redra_mcp.models import (
    ATTRIBUTION,
    DISCLAIMER,
    DatasetInfo,
    SearchQuery,
    SearchResponse,
    SettlementRecord,
)


class SQLiteProvider:
    name = "local-sqlite"

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.connection = connect(database_path)

    @staticmethod
    def _fts_expression(keywords: list[str]) -> str | None:
        phrases: list[str] = []
        for keyword in keywords:
            tokens = re.findall(r"[\w]+", keyword, flags=re.UNICODE)
            if tokens:
                phrase = " ".join(tokens).replace('"', '""')
                phrases.append(f'"{phrase}"')
        return " AND ".join(phrases) or None

    @staticmethod
    def _record(row: sqlite3.Row) -> SettlementRecord:
        data = dict(row)
        data.pop("rank", None)
        if data["normalized_status"] == "verified":
            data["normalized_status"] = "unknown"
        data["applicable_states"] = json.loads(data["applicable_states"] or "[]")
        data["quality_flags"] = json.loads(data["quality_flags"] or "[]")
        return SettlementRecord.model_validate(data)

    def search(self, query: SearchQuery) -> SearchResponse:
        joins: list[str] = []
        where: list[str] = []
        params: list[Any] = []
        fts = self._fts_expression(query.keywords)
        rank_column = "0 AS rank"
        if fts:
            joins.append("JOIN settlements_fts ON settlements_fts.id = s.id")
            where.append("settlements_fts MATCH ?")
            params.append(fts)
            rank_column = "bm25(settlements_fts) AS rank"
        if query.status:
            where.append("s.normalized_status = ?")
            params.append(query.status)
        if query.settlement_type:
            where.append("s.settlement_type = ?")
            params.append(query.settlement_type)
        if query.state:
            where.append("(s.applicable_states = '[]' OR s.applicable_states LIKE ?)")
            params.append(f'%"{query.state}"%')
        if query.proof_required:
            where.append("s.proof_required = ?")
            params.append(query.proof_required)
        if query.deadline_after:
            where.append("s.claim_deadline >= ?")
            params.append(query.deadline_after.isoformat())
        if query.deadline_before:
            where.append("s.claim_deadline <= ?")
            params.append(query.deadline_before.isoformat())

        join_sql = " ".join(joins)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        count = self.connection.execute(
            f"SELECT COUNT(*) FROM settlements s {join_sql} {where_sql}", params
        ).fetchone()[0]
        rows = self.connection.execute(
            f"""
            SELECT s.*, {rank_column}
            FROM settlements s
            {join_sql}
            {where_sql}
            ORDER BY rank ASC,
                     CASE s.source_kind
                         WHEN 'administrator' THEN 0
                         WHEN 'court' THEN 0
                         WHEN 'government' THEN 0
                         WHEN 'unknown' THEN 1
                         ELSE 2
                     END ASC,
                     s.claim_deadline IS NULL ASC,
                     s.claim_deadline ASC,
                     s.title ASC
            LIMIT ?
            """,
            [*params, query.limit],
        ).fetchall()
        return SearchResponse(
            query=query,
            count=count,
            items=[self._record(row) for row in rows],
            provider=self.name,
            attribution=ATTRIBUTION,
            disclaimer=DISCLAIMER,
        )

    def search_many(self, queries: list[SearchQuery]) -> list[SearchResponse]:
        return [self.search(query) for query in queries]

    def get(self, settlement_id: str) -> SettlementRecord | None:
        normalized_id = settlement_id.rstrip("/").rsplit("/", 1)[-1]
        row = self.connection.execute(
            "SELECT * FROM settlements WHERE id = ?", (normalized_id,)
        ).fetchone()
        return self._record(row) if row else None

    def get_many(
        self, settlement_ids: list[str]
    ) -> tuple[list[SettlementRecord], list[str]]:
        items: list[SettlementRecord] = []
        not_found: list[str] = []
        for settlement_id in settlement_ids:
            record = self.get(settlement_id)
            if record is None:
                not_found.append(settlement_id)
            else:
                items.append(record)
        return items, not_found

    def info(self) -> DatasetInfo:
        metadata = {
            row["key"]: row["value"]
            for row in self.connection.execute("SELECT key, value FROM metadata")
        }
        counts = self.connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN normalized_status = 'open' THEN 1 ELSE 0 END) AS open
            FROM settlements
            """
        ).fetchone()
        return DatasetInfo(
            provider=self.name,
            record_count=counts["total"],
            open_record_count=counts["open"] or 0,
            dataset_generated_at=metadata.get("dataset_generated_at") or None,
            dataset_modified_at=metadata.get("dataset_modified_at") or None,
            imported_at=metadata.get("imported_at") or None,
            source_url=metadata.get("source_url")
            or "https://settlesignal.com/data/settlements.json",
            attribution=metadata.get("source_attribution") or ATTRIBUTION,
            schema_version=int(metadata.get("schema_version", SCHEMA_VERSION)),
        )

    def close(self) -> None:
        self.connection.close()
