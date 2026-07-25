from __future__ import annotations

import pytest


@pytest.fixture
def settlesignal_payload() -> dict:
    return {
        "count": 2,
        "generated": "2026-07-24T00:00:00+00:00",
        "dateModified": "2026-07-23T00:00:00+00:00",
        "source": "https://settlesignal.com/data/settlements.json",
        "attribution": "SettleSignal — verified settlement intelligence",
        "settlements": [
            {
                "@id": "https://settlesignal.com/settlements/acme-data-breach/",
                "title": "Acme Data Breach Settlement",
                "url": "https://settlesignal.com/settlements/acme-data-breach/",
                "category": "Data breach",
                "settlement_type": "data_breach_settlement",
                "status": "Open for claims",
                "claim_deadline": "2026-10-01",
                "proof_required": "optional",
                "applicable_states": [],
                "official_claim_url": "https://claims.example/acme",
                "official_settlement_url": "https://claims.example/acme",
                "estimated_payout": "Up to $2,500 and credit monitoring",
                "verification_status": "official_source_found",
                "last_verified": "2026-07-23",
            },
            {
                "@id": "https://settlesignal.com/settlements/example-wages/",
                "title": "Example California Wage Settlement",
                "url": "https://settlesignal.com/settlements/example-wages/",
                "category": "Labor",
                "settlement_type": "class_action_settlement",
                "status": "Claim window closed",
                "claim_deadline": "2025-01-01",
                "proof_required": "no",
                "applicable_states": ["CA"],
                "official_claim_url": None,
                "official_settlement_url": "https://claims.example/wages",
                "estimated_payout": "Varies",
                "verification_status": "official_source_found",
                "last_verified": "2026-07-20",
            },
        ],
    }
