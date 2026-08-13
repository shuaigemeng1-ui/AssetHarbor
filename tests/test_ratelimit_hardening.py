"""Security regressions for mixed-duration in-process rate limits."""

import pytest
from fastapi import HTTPException

import app.services.ratelimit as ratelimit


def test_long_window_survives_one_hour_pruning(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now)
    ratelimit.check_rate_limit("daily", 1, 86400)

    now += 3601
    with pytest.raises(HTTPException) as rejected:
        ratelimit.check_rate_limit("daily", 1, 86400)
    assert rejected.value.status_code == 429


def test_high_cardinality_does_not_clear_existing_windows(monkeypatch):
    monkeypatch.setattr(ratelimit, "_MAX_WINDOWS", 2)
    ratelimit.check_rate_limit("victim", 1, 60)
    ratelimit.check_rate_limit("other", 1, 60)

    with pytest.raises(HTTPException) as new_identity:
        ratelimit.check_rate_limit("attacker", 1, 60)
    assert new_identity.value.status_code == 429
    with pytest.raises(HTTPException) as victim:
        ratelimit.check_rate_limit("victim", 1, 60)
    assert victim.value.status_code == 429


def test_long_window_capacity_cannot_block_login_or_media_windows(monkeypatch):
    monkeypatch.setattr(ratelimit, "_MAX_LONG_WINDOWS", 1)
    ratelimit.check_rate_limit("api-key-mutation:first", 1, 86400)
    with pytest.raises(HTTPException):
        ratelimit.check_rate_limit("api-key-mutation:second", 1, 86400)

    ratelimit.check_rate_limit("login-user:normal", 1, 60)


def test_pruning_scan_is_coarsely_throttled_for_staggered_windows(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now)
    ratelimit.check_rate_limit("first", 5, 60)
    ratelimit.check_rate_limit("second", 5, 60)

    class CountingDict(dict):
        scans = 0

        def items(self):
            self.scans += 1
            return super().items()

    guarded = CountingDict(ratelimit._WINDOWS)
    monkeypatch.setattr(ratelimit, "_WINDOWS", guarded)
    now += 1
    ratelimit.check_rate_limit("first", 5, 60)
    for _ in range(10):
        now += 0.05
        ratelimit.check_rate_limit("first", 20, 60)
    assert guarded.scans == 1
