from __future__ import annotations

import asyncio

from redra_mcp.http import (
    ConcurrencyLimitMiddleware,
    IPRateLimitMiddleware,
    RequestBodyLimitMiddleware,
)


async def ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def request(
    middleware,
    ip: str = "127.0.0.1",
    fly_ip: str | None = None,
    body: bytes = b"",
):
    messages = []
    headers = [] if fly_ip is None else [(b"fly-client-ip", fly_ip.encode())]
    scope = {"type": "http", "client": (ip, 1234), "headers": headers}

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    asyncio.run(middleware(scope, receive, send))
    return messages


def test_mcp_edge_rate_limit():
    limiter = IPRateLimitMiddleware(ok_app, limit=1)
    assert request(limiter)[0]["status"] == 200
    assert request(limiter)[0]["status"] == 429


def test_trusted_fly_ips_have_separate_buckets():
    limiter = IPRateLimitMiddleware(ok_app, limit=1, trust_fly_headers=True)
    assert request(limiter, fly_ip="203.0.113.1")[0]["status"] == 200
    assert request(limiter, fly_ip="203.0.113.2")[0]["status"] == 200


def test_concurrency_limit_rejects_excess_in_flight_request():
    limiter = ConcurrencyLimitMiddleware(ok_app, limit=1)
    assert limiter._acquire() is True
    try:
        assert request(limiter)[0]["status"] == 503
    finally:
        limiter._release()
    assert request(limiter)[0]["status"] == 200


def test_request_body_limit_rejects_oversized_payload():
    limiter = RequestBodyLimitMiddleware(ok_app, max_bytes=4)
    assert request(limiter, body=b"1234")[0]["status"] == 200
    assert request(limiter, body=b"12345")[0]["status"] == 413
