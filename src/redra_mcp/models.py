from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


ClaimStatus = Literal["open", "upcoming", "closed", "payment", "unknown"]
SearchStatus = Literal["open", "upcoming"]
VerificationStatus = Literal[
    "administrator_verified",
    "court_verified",
    "needs_recheck",
    "official_source_found",
    "third_party_only",
]
SourceKind = Literal["administrator", "court", "government", "secondary", "unknown"]
Claimability = Literal[
    "claim_open", "upcoming", "claim_closed", "automatic_payment", "unknown"
]
QualityFlag = Literal[
    "missing_deadline",
    "missing_claim_url",
    "non_lifecycle_source_status",
    "secondary_settlement_url",
    "secondary_source_only",
    "source_check_missing",
    "stale_source_check",
    "status_deadline_conflict",
]
SettlementType = Literal[
    "class_action_settlement",
    "consumer_product_settlement",
    "data_breach_settlement",
    "financial_fee_settlement",
    "government_refund",
    "other_consumer_compensation",
    "privacy_settlement",
    "regulatory_compensation_program",
    "state_ag_refund",
]
ProofRequirement = Literal["yes", "no", "optional", "varies", "unknown"]

SOURCE_NAME = "SettleSignal"
SOURCE_DATASET_URL = "https://huggingface.co/datasets/katana957/us-settlement-catalog"
SOURCE_LICENSE = "CC BY 4.0"
SOURCE_LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
SOURCE_CHANGES = (
    "Redra normalizes source fields and adds derived lifecycle and quality metadata."
)
ATTRIBUTION = (
    "Data adapted from SettleSignal — verified settlement intelligence "
    "(https://settlesignal.com/). Source dataset: "
    f"{SOURCE_DATASET_URL}. Licensed under {SOURCE_LICENSE} "
    f"({SOURCE_LICENSE_URL}). {SOURCE_CHANGES}"
)
REDRA_SOURCE_NAME = "Redra"
REDRA_SOURCE_DATASET_URL = "https://data.redra.ai/catalog/v1/manifest.json"
REDRA_SOURCE_LICENSE = "CC-BY-4.0"
REDRA_SOURCE_CHANGES = (
    "Redra independently collects, validates, deduplicates, and normalizes factual "
    "settlement metadata from linked court, government, and settlement-administrator "
    "sources."
)
REDRA_ATTRIBUTION = (
    "Redra independently collects and normalizes factual settlement metadata from "
    "linked court, government, and settlement-administrator sources."
)
DISCLAIMER = (
    "Potential match only. Confirm eligibility, deadlines, and filing instructions "
    "with the official settlement administrator. Redra does not provide legal advice."
)


class SearchQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keywords: list[Annotated[str, Field(min_length=1, max_length=100)]] = Field(
        default_factory=list,
        max_length=20,
        description=(
            "Terms combined with logical AND. Put unrelated companies, products, "
            "or alternatives in separate batch query objects."
        ),
    )
    state: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Za-z]{2}$",
        description="Optional two-letter US postal abbreviation, such as CA.",
    )
    status: SearchStatus = Field(
        default="open",
        description=(
            "Public lifecycle filter: open or upcoming. Defaults to open. Upcoming "
            "records are not yet claimable and belong in a separate watchlist."
        ),
    )
    settlement_type: SettlementType | None = Field(
        default=None,
        description=(
            "Exact settlement taxonomy filter. Use this instead of keywords for "
            "type concepts such as privacy, data breaches, or financial fees."
        ),
    )
    proof_required: ProofRequirement | None = Field(
        default=None,
        description="Exact proof requirement: yes, no, optional, varies, or unknown.",
    )
    deadline_after: date | None = Field(
        default=None,
        description="Include deadlines on or after this ISO 8601 date.",
    )
    deadline_before: date | None = Field(
        default=None,
        description="Include deadlines on or before this ISO 8601 date.",
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum results for this independent query, from 1 to 50.",
    )

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        seen: set[str] = set()
        for item in value:
            item = " ".join(item.strip().split())
            key = item.casefold()
            if item and key not in seen:
                cleaned.append(item[:100])
                seen.add(key)
        return cleaned

    @field_validator("state")
    @classmethod
    def clean_state(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        value = value.strip().upper()
        if len(value) != 2 or not value.isalpha():
            raise ValueError("state must be a two-letter US postal abbreviation")
        return value

    @field_validator("proof_required", mode="before")
    @classmethod
    def clean_proof(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().lower()
            return value or None
        return value


class SettlementRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    description: str = ""
    eligibility: str = ""
    category: str = ""
    settlement_type: str = ""
    status: str
    normalized_status: ClaimStatus
    claim_deadline: date | None = None
    proof_required: str = "unknown"
    applicable_states: list[str] = Field(default_factory=list)
    official_claim_url: str | None = None
    official_settlement_url: str | None = None
    estimated_payout: str | None = None
    published_amount_cents: int | None = None
    source_verification_status: VerificationStatus | None = None
    source_checked_at: date | None = None
    source_kind: SourceKind = "unknown"
    claimability: Claimability = "unknown"
    claim_url_available: bool = False
    quality_flags: list[QualityFlag] = Field(default_factory=list)
    lifecycle_stage: str | None = None
    provenance_tier: Literal["A", "B"] | None = None
    independently_discovered: bool = False
    include_in_claimable_total: bool = False
    future_claim_window_evidenced: bool = False
    source_url: str
    source_name: str = SOURCE_NAME
    source_license: str = SOURCE_LICENSE
    source_license_url: str = SOURCE_LICENSE_URL
    source_attribution: str = ATTRIBUTION
    source_changes: str = SOURCE_CHANGES


class SearchResponse(BaseModel):
    query: SearchQuery
    count: int
    items: list[SettlementRecord]
    provider: str
    attribution: str
    disclaimer: str


class DatasetInfo(BaseModel):
    provider: str
    record_count: int
    open_record_count: int
    upcoming_record_count: int = 0
    dataset_generated_at: str | None = None
    dataset_modified_at: str | None = None
    imported_at: str | None = None
    source_url: str
    source_name: str = SOURCE_NAME
    source_license: str = SOURCE_LICENSE
    source_license_url: str = SOURCE_LICENSE_URL
    source_dataset_url: str = SOURCE_DATASET_URL
    source_changes: str = SOURCE_CHANGES
    attribution: str
    schema_version: int = 2
    extra: dict[str, Any] = Field(default_factory=dict)
