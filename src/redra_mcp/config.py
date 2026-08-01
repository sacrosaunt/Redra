from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_DATASET_URL = "https://data.redra.ai/catalog/v1/manifest.json"


@dataclass(frozen=True, slots=True)
class Settings:
    database_path: Path
    dataset_url: str
    request_timeout: float
    host: str
    port: int
    rate_limit_per_hour: int
    trust_fly_headers: bool
    max_concurrent_requests: int
    max_request_body_bytes: int
    search_cache_ttl_seconds: float
    search_cache_max_entries: int

    @classmethod
    def from_env(cls) -> "Settings":
        default_db = Path.home() / ".local" / "share" / "redra" / "settlements.db"
        return cls(
            database_path=Path(os.getenv("REDRA_DATABASE_PATH", str(default_db))).expanduser(),
            dataset_url=os.getenv(
                "REDRA_DATASET_URL",
                os.getenv("REDRA_SETTLESIGNAL_URL", DEFAULT_DATASET_URL),
            ),
            request_timeout=float(os.getenv("REDRA_REQUEST_TIMEOUT", "20")),
            host=os.getenv("REDRA_HOST", "127.0.0.1"),
            port=int(os.getenv("PORT", os.getenv("REDRA_PORT", "8000"))),
            rate_limit_per_hour=int(os.getenv("REDRA_RATE_LIMIT_PER_HOUR", "0")),
            trust_fly_headers=os.getenv("REDRA_TRUST_FLY_HEADERS", "false").lower()
            in {"1", "true", "yes"},
            max_concurrent_requests=int(
                os.getenv("REDRA_MAX_CONCURRENT_REQUESTS", "0")
            ),
            max_request_body_bytes=int(
                os.getenv("REDRA_MAX_REQUEST_BODY_BYTES", "1048576")
            ),
            search_cache_ttl_seconds=float(
                os.getenv("REDRA_SEARCH_CACHE_TTL_SECONDS", "30")
            ),
            search_cache_max_entries=int(
                os.getenv("REDRA_SEARCH_CACHE_MAX_ENTRIES", "512")
            ),
        )
