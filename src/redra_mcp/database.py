from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from redra_mcp.models import SettlementRecord


SCHEMA_VERSION = 3


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    initialize_schema(connection)
    return connection


def initialize_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS settlements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            eligibility TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '',
            settlement_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            normalized_status TEXT NOT NULL,
            claim_deadline TEXT,
            proof_required TEXT NOT NULL DEFAULT 'unknown',
            applicable_states TEXT NOT NULL DEFAULT '[]',
            official_claim_url TEXT,
            official_settlement_url TEXT,
            estimated_payout TEXT,
            published_amount_cents INTEGER,
            source_verification_status TEXT,
            source_checked_at TEXT,
            source_kind TEXT NOT NULL DEFAULT 'unknown',
            claimability TEXT NOT NULL DEFAULT 'unknown',
            claim_url_available INTEGER NOT NULL DEFAULT 0,
            quality_flags TEXT NOT NULL DEFAULT '[]',
            lifecycle_stage TEXT,
            provenance_tier TEXT,
            independently_discovered INTEGER NOT NULL DEFAULT 0,
            include_in_claimable_total INTEGER NOT NULL DEFAULT 0,
            future_claim_window_evidenced INTEGER NOT NULL DEFAULT 0,
            source_url TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_license TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_settlements_status
            ON settlements(normalized_status);
        CREATE INDEX IF NOT EXISTS idx_settlements_deadline
            ON settlements(claim_deadline);
        CREATE INDEX IF NOT EXISTS idx_settlements_type
            ON settlements(settlement_type);

        CREATE VIRTUAL TABLE IF NOT EXISTS settlements_fts USING fts5(
            id UNINDEXED,
            title,
            description,
            eligibility,
            category,
            estimated_payout,
            tokenize = 'unicode61 remove_diacritics 2'
        );

        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        """
    )
    columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(settlements)")
    }
    additions = {
        "description": "TEXT NOT NULL DEFAULT ''",
        "eligibility": "TEXT NOT NULL DEFAULT ''",
        "source_verification_status": "TEXT",
        "source_checked_at": "TEXT",
        "source_kind": "TEXT NOT NULL DEFAULT 'unknown'",
        "claimability": "TEXT NOT NULL DEFAULT 'unknown'",
        "claim_url_available": "INTEGER NOT NULL DEFAULT 0",
        "quality_flags": "TEXT NOT NULL DEFAULT '[]'",
        "published_amount_cents": "INTEGER",
        "lifecycle_stage": "TEXT",
        "provenance_tier": "TEXT",
        "independently_discovered": "INTEGER NOT NULL DEFAULT 0",
        "include_in_claimable_total": "INTEGER NOT NULL DEFAULT 0",
        "future_claim_window_evidenced": "INTEGER NOT NULL DEFAULT 0",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE settlements ADD COLUMN {name} {declaration}"
            )
    if "verification_status" in columns:
        connection.execute(
            "UPDATE settlements SET source_verification_status = verification_status "
            "WHERE source_verification_status IS NULL"
        )
    if "last_verified" in columns:
        connection.execute(
            "UPDATE settlements SET source_checked_at = last_verified "
            "WHERE source_checked_at IS NULL"
        )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_settlements_source_kind "
        "ON settlements(source_kind)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_settlements_claimability "
        "ON settlements(claimability)"
    )
    fts_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(settlements_fts)")
    }
    if not {"description", "eligibility"} <= fts_columns:
        connection.execute("DROP TABLE settlements_fts")
        connection.execute(
            """
            CREATE VIRTUAL TABLE settlements_fts USING fts5(
                id UNINDEXED,
                title,
                description,
                eligibility,
                category,
                estimated_payout,
                tokenize = 'unicode61 remove_diacritics 2'
            )
            """
        )
        connection.execute(
            """
            INSERT INTO settlements_fts(
                id, title, description, eligibility, category, estimated_payout
            )
            SELECT id, title, description, eligibility, category,
                   COALESCE(estimated_payout, '')
            FROM settlements
            """
        )
    connection.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.execute(
        "UPDATE settlements SET normalized_status = 'unknown' "
        "WHERE normalized_status = 'verified'"
    )
    connection.commit()


def replace_records(
    connection: sqlite3.Connection,
    records: Iterable[SettlementRecord],
    metadata: dict[str, str | int | None],
) -> int:
    materialized = list(records)
    imported_at = datetime.now(UTC).isoformat()
    with connection:
        connection.execute("DELETE FROM settlements_fts")
        connection.execute("DELETE FROM settlements")
        for record in materialized:
            row = record.model_dump(mode="json")
            connection.execute(
                """
                INSERT INTO settlements (
                    id, title, description, eligibility, category,
                    settlement_type, status,
                    normalized_status, claim_deadline, proof_required,
                    applicable_states, official_claim_url,
                    official_settlement_url, estimated_payout,
                    published_amount_cents,
                    source_verification_status, source_checked_at,
                    source_kind, claimability, claim_url_available,
                    quality_flags, lifecycle_stage, provenance_tier,
                    independently_discovered, include_in_claimable_total,
                    future_claim_window_evidenced,
                    source_url, source_name, source_license
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["title"],
                    row["description"],
                    row["eligibility"],
                    row["category"],
                    row["settlement_type"],
                    row["status"],
                    row["normalized_status"],
                    row["claim_deadline"],
                    row["proof_required"],
                    json.dumps(row["applicable_states"], separators=(",", ":")),
                    row["official_claim_url"],
                    row["official_settlement_url"],
                    row["estimated_payout"],
                    row["published_amount_cents"],
                    row["source_verification_status"],
                    row["source_checked_at"],
                    row["source_kind"],
                    row["claimability"],
                    int(row["claim_url_available"]),
                    json.dumps(row["quality_flags"], separators=(",", ":")),
                    row["lifecycle_stage"],
                    row["provenance_tier"],
                    int(row["independently_discovered"]),
                    int(row["include_in_claimable_total"]),
                    int(row["future_claim_window_evidenced"]),
                    row["source_url"],
                    row["source_name"],
                    row["source_license"],
                ),
            )
            connection.execute(
                """
                INSERT INTO settlements_fts(
                    id, title, description, eligibility, category, estimated_payout
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"],
                    row["title"],
                    row["description"],
                    row["eligibility"],
                    row["category"],
                    row["estimated_payout"] or "",
                ),
            )

        values = dict(metadata)
        values["imported_at"] = imported_at
        values["record_count"] = len(materialized)
        values["schema_version"] = SCHEMA_VERSION
        for key, value in values.items():
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
                (key, "" if value is None else str(value)),
            )
    return len(materialized)
