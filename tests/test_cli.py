from __future__ import annotations

from redra_mcp import cli
from redra_mcp.config import Settings


def test_self_hosted_rate_limit_is_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv("REDRA_RATE_LIMIT_PER_HOUR", raising=False)
    monkeypatch.delenv("REDRA_MAX_CONCURRENT_REQUESTS", raising=False)
    monkeypatch.setenv("REDRA_DATABASE_PATH", str(tmp_path / "settlements.db"))
    assert Settings.from_env().rate_limit_per_hour == 0
    assert Settings.from_env().max_concurrent_requests == 0


def test_dataset_watch_updates_immediately(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("REDRA_DATABASE_PATH", str(tmp_path / "settlements.db"))
    monkeypatch.setattr(cli, "update_dataset", lambda *args, **kwargs: calls.append(1) or 2)
    monkeypatch.setattr(cli.time, "sleep", lambda seconds: (_ for _ in ()).throw(KeyboardInterrupt))
    assert cli.main(["dataset", "watch", "--interval-hours", "24"]) == 0
    assert calls == [1]
