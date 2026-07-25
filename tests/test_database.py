import sqlite3

from redra_mcp.database import connect


def test_existing_v1_database_is_migrated(tmp_path):
    path = tmp_path / "v1.db"
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE settlements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
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
            verification_status TEXT,
            last_verified TEXT,
            source_url TEXT NOT NULL,
            source_name TEXT NOT NULL,
            source_license TEXT NOT NULL
        );
        INSERT INTO settlements (
            id, title, status, normalized_status, verification_status,
            last_verified, source_url, source_name, source_license
        ) VALUES (
            'example', 'Example', 'Open for claims', 'open',
            'official_source_found', '2026-07-20',
            'https://example.test', 'SettleSignal', 'CC-BY-4.0'
        );
        """
    )
    connection.close()

    migrated = connect(path)
    try:
        columns = {
            row["name"] for row in migrated.execute("PRAGMA table_info(settlements)")
        }
        assert {
            "source_verification_status",
            "source_checked_at",
            "source_kind",
            "claimability",
            "claim_url_available",
            "quality_flags",
        } <= columns
        row = migrated.execute(
            "SELECT source_verification_status, source_checked_at, quality_flags "
            "FROM settlements WHERE id = 'example'"
        ).fetchone()
        assert row["source_verification_status"] == "official_source_found"
        assert row["source_checked_at"] == "2026-07-20"
        assert row["quality_flags"] == "[]"
    finally:
        migrated.close()
