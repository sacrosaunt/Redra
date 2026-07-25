from __future__ import annotations

import ipaddress
import json
import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class Window:
    started_at: int
    count: int


class IPRateLimitMiddleware:
    """Small ASGI fixed-window limiter for the hosted MCP edge."""

    def __init__(
        self,
        app: Any,
        *,
        limit: int,
        window_seconds: int = 3600,
        trust_fly_headers: bool = False,
    ):
        self.app = app
        self.limit = limit
        self.window_seconds = window_seconds
        self.trust_fly_headers = trust_fly_headers
        self._windows: dict[str, Window] = {}
        self._lock = threading.Lock()

    def _client_ip(self, scope: dict) -> str:
        candidate = (scope.get("client") or ("unknown", 0))[0]
        if self.trust_fly_headers:
            for name, value in scope.get("headers", []):
                if name.lower() == b"fly-client-ip":
                    candidate = value.decode("ascii", errors="ignore")
                    break
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            return "unknown"

    def _check(self, key: str) -> tuple[bool, int, int]:
        current = int(time.time())
        window_start = current - (current % self.window_seconds)
        reset = window_start + self.window_seconds
        with self._lock:
            bucket = self._windows.get(key)
            if bucket is None or bucket.started_at != window_start:
                bucket = Window(started_at=window_start, count=0)
                self._windows[key] = bucket
            bucket.count += 1
            remaining = max(0, self.limit - bucket.count)
            allowed = bucket.count <= self.limit
            if len(self._windows) > 10_000:
                self._windows = {
                    item_key: item
                    for item_key, item in self._windows.items()
                    if item.started_at == window_start
                }
        return allowed, remaining, reset

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or self.limit <= 0:
            await self.app(scope, receive, send)
            return

        allowed, remaining, reset = self._check(self._client_ip(scope))
        rate_headers = [
            (b"x-ratelimit-limit", str(self.limit).encode()),
            (b"x-ratelimit-remaining", str(remaining).encode()),
            (b"x-ratelimit-reset", str(reset).encode()),
        ]
        if not allowed:
            body = json.dumps(
                {
                    "error": "rate_limit_exceeded",
                    "message": "Too many MCP requests from this IP address.",
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 429,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", str(max(1, reset - int(time.time()))).encode()),
                        *rate_headers,
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message: dict) -> None:
            if message.get("type") == "http.response.start":
                message["headers"] = [*message.get("headers", []), *rate_headers]
            await send(message)

        await self.app(scope, receive, send_with_headers)


class ConcurrencyLimitMiddleware:
    """Reject excess in-flight HTTP requests before they reach MCP tools."""

    def __init__(self, app: Any, *, limit: int):
        self.app = app
        self.limit = limit
        self._active = 0
        self._lock = threading.Lock()

    def _acquire(self) -> bool:
        with self._lock:
            if self.limit > 0 and self._active >= self.limit:
                return False
            self._active += 1
            return True

    def _release(self) -> None:
        with self._lock:
            self._active = max(0, self._active - 1)

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or self.limit <= 0:
            await self.app(scope, receive, send)
            return
        if not self._acquire():
            body = json.dumps(
                {
                    "error": "server_busy",
                    "message": "The MCP server has reached its concurrent request limit.",
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 503,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(body)).encode()),
                        (b"retry-after", b"1"),
                        (b"x-concurrency-limit", str(self.limit).encode()),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        try:
            await self.app(scope, receive, send)
        finally:
            self._release()
