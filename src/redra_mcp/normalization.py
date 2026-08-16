from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from redra_mcp.models import (
    ATTRIBUTION,
    REDRA_ATTRIBUTION,
    REDRA_SOURCE_CHANGES,
    SOURCE_CHANGES,
    SOURCE_LICENSE_URL,
    SettlementRecord,
)


SECONDARY_SOURCE_HOSTS = {
    "claimdepot.com",
    "classaction.org",
    "openclassactions.com",
    "prnewswire.com",
    "topclassactions.com",
}
ADMINISTRATOR_HOST_MARKERS = ("claim", "settlement", "dataincident")
KNOWN_ADMINISTRATOR_HOSTS = {
    "angeiongroup.com",
    "cptgroup.com",
    "cptgroupcaseinfo.com",
    "epiqglobal.com",
    "jndla.com",
    "kroll.com",
    "simpluris.com",
    "strategicclaims.net",
}
MAX_URL_LENGTH = 2_048
VALID_VERIFICATION_STATUSES = {
    "administrator_verified",
    "court_verified",
    "needs_recheck",
    "official_source_found",
    "third_party_only",
}
PROOF_YES_VALUES = {
    "yes",
    "true",
    "required",
    "documentation_required",
    "attestation_only",
    "notice_id_or_pin",
}
PROOF_NO_VALUES = {"no", "false", "none", "not_required"}


def clean_text(value: Any, *, max_length: int, default: str = "") -> str:
    if not isinstance(value, (str, int, float)):
        return default
    cleaned = " ".join(str(value).split())
    return cleaned[:max_length] or default


def normalize_proof_requirement(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    cleaned = clean_text(value, max_length=32, default="unknown").casefold()
    if cleaned in PROOF_YES_VALUES:
        return "yes"
    if cleaned in PROOF_NO_VALUES:
        return "no"
    return "unknown"


def safe_url(value: Any, *, allowed_hosts: set[str] | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > MAX_URL_LENGTH:
        return None
    try:
        parsed = urlparse(cleaned)
        host = (parsed.hostname or "").casefold().removeprefix("www.")
        if (
            parsed.scheme not in {"http", "https"}
            or not host
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
    except ValueError:
        return None
    if host == "localhost" or host.endswith(".local"):
        return None
    try:
        if not ip_address(host).is_global:
            return None
    except ValueError:
        pass
    if allowed_hosts and not _host_matches(host, allowed_hosts):
        return None
    return cleaned


def current_us_date() -> date:
    try:
        return datetime.now(ZoneInfo("America/Los_Angeles")).date()
    except ZoneInfoNotFoundError:
        return (datetime.now(UTC) - timedelta(hours=8)).date()


def _host(value: str | None) -> str:
    try:
        return (urlparse(value or "").hostname or "").casefold().removeprefix("www.")
    except ValueError:
        return ""


def _host_matches(host: str, candidates: set[str]) -> bool:
    return any(
        host == candidate or host.endswith(f".{candidate}")
        for candidate in candidates
    )


def _is_court_host(host: str) -> bool:
    return host.endswith("uscourts.gov") or (
        host.endswith(".gov") and (host.startswith("court.") or ".courts." in host)
    )


def _is_government_host(host: str) -> bool:
    return host.endswith(".gov") or host.endswith(".mil")


def _is_secondary_host(host: str) -> bool:
    return _host_matches(host, SECONDARY_SOURCE_HOSTS)


def claim_url_available(value: str | None) -> bool:
    cleaned = safe_url(value)
    if not cleaned:
        return False
    parsed = urlparse(cleaned)
    path = parsed.path.casefold().rstrip("/")
    if _is_government_host(_host(value)) and path.endswith(
        "/refund-programs-frequently-asked-questions"
    ):
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


def derive_source_kind(
    official_settlement_url: str | None, official_claim_url: str | None
) -> str:
    settlement_host = _host(official_settlement_url)
    claim_host = (
        _host(official_claim_url) if claim_url_available(official_claim_url) else ""
    )
    hosts = [host for host in (claim_host, settlement_host) if host]
    if any(_is_court_host(host) for host in hosts):
        return "court"
    if any(_is_government_host(host) for host in hosts):
        return "government"
    if claim_host and not _is_secondary_host(claim_host):
        return "administrator"
    if settlement_host and _is_secondary_host(settlement_host):
        return "secondary"
    if settlement_host and (
        _host_matches(settlement_host, KNOWN_ADMINISTRATOR_HOSTS)
        or any(marker in settlement_host for marker in ADMINISTRATOR_HOST_MARKERS)
    ):
        return "administrator"
    return "unknown"


def _parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def derive_claimability(
    raw_status: str | None,
    claim_deadline: str | None,
    settlement_type: str | None,
    has_claim_url: bool,
    *,
    today: date,
) -> str:
    status = (raw_status or "").strip().casefold()
    deadline = _parse_date(claim_deadline)
    if status in {"payments started", "payment pending"}:
        return "automatic_payment"
    if status == "upcoming":
        return "upcoming"
    if status == "claim window closed":
        return "claim_closed"
    if status == "open for claims":
        if settlement_type == "government_refund" and not has_claim_url:
            return "automatic_payment"
        return "claim_closed" if deadline and deadline < today else "claim_open"
    if status == "verified record":
        if deadline and deadline >= today:
            return "claim_open"
        if deadline and deadline < today:
            return "claim_closed"
    if (
        settlement_type == "government_refund"
        and not has_claim_url
        and deadline is None
    ):
        return "automatic_payment"
    return "unknown"


def status_for_claimability(value: str) -> str:
    return {
        "claim_open": "open",
        "claim_closed": "closed",
        "automatic_payment": "payment",
        "upcoming": "upcoming",
    }.get(value, "unknown")


def derive_quality_flags(
    raw: dict[str, Any],
    *,
    today: date,
    source_kind: str,
    claimability: str,
    has_claim_url: bool,
) -> list[str]:
    flags: list[str] = []
    raw_status = str(raw.get("status") or "").strip().casefold()
    deadline = _parse_date(raw.get("claim_deadline"))
    settlement_host = _host(raw.get("official_settlement_url"))
    checked_at = _parse_date(raw.get("last_verified"))
    if claimability == "claim_open" and deadline is None:
        flags.append("missing_deadline")
    if claimability == "claim_open" and not has_claim_url:
        flags.append("missing_claim_url")
    if raw_status == "verified record":
        flags.append("non_lifecycle_source_status")
    if (
        raw_status == "open for claims" and deadline and deadline < today
    ) or (
        raw_status == "claim window closed" and deadline and deadline >= today
    ):
        flags.append("status_deadline_conflict")
    if settlement_host and _is_secondary_host(settlement_host):
        flags.append("secondary_settlement_url")
    if source_kind == "secondary":
        flags.append("secondary_source_only")
    if checked_at is None:
        flags.append("source_check_missing")
    elif checked_at < today - timedelta(days=30):
        flags.append("stale_source_check")
    return flags


def normalize_status(value: str | None) -> str:
    claimability = derive_claimability(value, None, None, False, today=date.today())
    return status_for_claimability(claimability)


def record_id(raw: dict[str, Any]) -> str:
    supplied = clean_text(raw.get("id"), max_length=160)
    if supplied:
        return supplied
    url = safe_url(
        raw.get("url") or raw.get("@id"), allowed_hosts={"settlesignal.com"}
    ) or ""
    path = urlparse(url).path.rstrip("/")
    if path:
        return path.rsplit("/", 1)[-1][:160]
    title = clean_text(raw.get("title"), max_length=300, default="settlement")
    slug = "-".join(
        part for part in title.casefold().replace("_", " ").split() if part
    )
    return slug[:160] or "settlement"


def normalize_record(raw: dict[str, Any], *, today: date | None = None) -> SettlementRecord:
    active_date = today or current_us_date()
    redra_record = bool(clean_text(raw.get("id"), max_length=160).startswith("redra-"))
    source_url = (
        safe_url(raw.get("source_url"))
        if redra_record
        else safe_url(
            raw.get("url") or raw.get("@id"), allowed_hosts={"settlesignal.com"}
        )
    ) or ("https://redra.ai" if redra_record else "https://settlesignal.com/")
    raw_states = raw.get("applicable_states", [])
    states = []
    if isinstance(raw_states, list):
        for state in raw_states[:60]:
            normalized_state = clean_text(state, max_length=2).upper()
            if (
                len(normalized_state) == 2
                and normalized_state.isalpha()
                and normalized_state not in states
            ):
                states.append(normalized_state)
    official_claim_url = safe_url(raw.get("official_claim_url"))
    official_settlement_url = safe_url(raw.get("official_settlement_url"))
    has_claim_url = claim_url_available(official_claim_url)
    supplied_source_kind = clean_text(raw.get("source_kind"), max_length=32)
    source_kind = (
        supplied_source_kind
        if redra_record
        and supplied_source_kind in {"administrator", "court", "government"}
        else derive_source_kind(official_settlement_url, official_claim_url)
    )
    status = clean_text(raw.get("status"), max_length=80, default="Unknown")
    settlement_type = clean_text(raw.get("settlement_type"), max_length=80)
    claim_deadline = _parse_date(clean_text(raw.get("claim_deadline"), max_length=10))
    claimability = derive_claimability(
        status,
        claim_deadline.isoformat() if claim_deadline else None,
        settlement_type,
        has_claim_url,
        today=active_date,
    )
    sanitized = {
        **raw,
        "status": status,
        "claim_deadline": claim_deadline.isoformat() if claim_deadline else None,
        "official_claim_url": official_claim_url,
        "official_settlement_url": official_settlement_url,
        "last_verified": clean_text(
            raw.get("source_checked_at") or raw.get("last_verified"), max_length=10
        ),
    }
    proof_required = normalize_proof_requirement(raw.get("proof_required"))
    verification_status = clean_text(
        raw.get("source_verification_status") or raw.get("verification_status"),
        max_length=40,
    ).casefold()
    if verification_status not in VALID_VERIFICATION_STATUSES:
        verification_status = None
    source_checked_at = _parse_date(sanitized["last_verified"])
    return SettlementRecord(
        id=record_id(raw),
        title=clean_text(
            raw.get("title"), max_length=300, default="Untitled settlement"
        ),
        description=clean_text(raw.get("description"), max_length=1_500),
        eligibility=clean_text(raw.get("eligibility"), max_length=1_500),
        category=clean_text(raw.get("category"), max_length=100),
        settlement_type=settlement_type,
        status=status,
        normalized_status=status_for_claimability(claimability),
        claim_deadline=claim_deadline,
        proof_required=proof_required,
        applicable_states=states,
        official_claim_url=official_claim_url,
        official_settlement_url=official_settlement_url,
        expected_individual_payout=clean_text(
            raw.get("expected_individual_payout"),
            max_length=2_000,
        ) or None,
        maximum_cumulative_payout_cents=(
            raw.get("maximum_cumulative_payout_cents")
            if isinstance(raw.get("maximum_cumulative_payout_cents"), int)
            and not isinstance(raw.get("maximum_cumulative_payout_cents"), bool)
            and raw.get("maximum_cumulative_payout_cents") > 0
            else None
        ),
        source_verification_status=verification_status,
        source_checked_at=source_checked_at,
        source_kind=source_kind,
        claimability=claimability,
        claim_url_available=has_claim_url,
        quality_flags=derive_quality_flags(
            sanitized,
            today=active_date,
            source_kind=source_kind,
            claimability=claimability,
            has_claim_url=has_claim_url,
        ),
        lifecycle_stage=clean_text(raw.get("lifecycle_stage"), max_length=64) or None,
        provenance_tier=(
            raw.get("provenance_tier")
            if raw.get("provenance_tier") in {"A", "B"}
            else None
        ),
        independently_discovered=bool(raw.get("independently_discovered")),
        include_in_claimable_total=bool(raw.get("include_in_claimable_total")),
        future_claim_window_evidenced=bool(
            raw.get("future_claim_window_evidenced")
        ),
        source_url=source_url,
        source_name=clean_text(
            raw.get("source_name"), max_length=100,
            default="Redra" if redra_record else "SettleSignal",
        ),
        source_license=clean_text(
            raw.get("source_license"), max_length=100, default="CC BY 4.0"
        ),
        source_license_url=SOURCE_LICENSE_URL,
        source_attribution=REDRA_ATTRIBUTION if redra_record else ATTRIBUTION,
        source_changes=REDRA_SOURCE_CHANGES if redra_record else SOURCE_CHANGES,
    )
