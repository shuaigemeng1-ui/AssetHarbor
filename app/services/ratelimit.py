"""In-process fixed-window rate limiter.

Suited to the single-container deployment. For horizontal scaling, replace
this with a shared store (e.g. Redis) — only the ``check_rate_limit`` call
sites need to change.
"""

import time
from threading import Lock

from fastapi import HTTPException, Request

# key -> (window_start, count, configured_window_seconds)
_WINDOWS: dict[str, tuple[float, int, int]] = {}
_LONG_WINDOWS: dict[str, tuple[float, int, int]] = {}
_LOCK = Lock()
_MAX_WINDOWS = 10_000
_MAX_LONG_WINDOWS = 10_000
_NEXT_PRUNE_AT = {"short": 0.0, "long": 0.0}
_PRUNE_INTERVAL_SECONDS = 1.0


def _prune(
    windows: dict[str, tuple[float, int, int]], pool_name: str, now: float
) -> None:
    """Remove expired dimensions at most once per coarse pruning interval."""
    if not windows:
        _NEXT_PRUNE_AT[pool_name] = now + _PRUNE_INTERVAL_SECONDS
        return
    if now < _NEXT_PRUNE_AT[pool_name]:
        return
    stale = [
        key
        for key, (start, _count, window_seconds) in windows.items()
        if now - start >= window_seconds
    ]
    for key in stale:
        del windows[key]
    # A one-second fail-closed delay at capacity is preferable to allowing a
    # staggered high-cardinality workload to force a full-table scan on every
    # request as successive dimensions expire.
    _NEXT_PRUNE_AT[pool_name] = now + _PRUNE_INTERVAL_SECONDS


def check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    """Raise HTTP 429 when ``key`` exceeds ``limit`` requests per window."""
    if limit <= 0:
        return
    now = time.monotonic()
    with _LOCK:
        # Long-lived credential-governance windows use an independent pool so
        # many accounts cannot occupy every slot needed by login/media limits.
        windows = _LONG_WINDOWS if window_seconds > 3600 else _WINDOWS
        pool_name = "long" if windows is _LONG_WINDOWS else "short"
        capacity = _MAX_LONG_WINDOWS if windows is _LONG_WINDOWS else _MAX_WINDOWS
        _prune(windows, pool_name, now)
        if key not in windows and len(windows) >= capacity:
            # Never clear every limiter window: an attacker could otherwise
            # manufacture high-cardinality usernames/IPs to reset a victim's
            # login or credential-mutation protection. Reject only the new
            # dimension while established windows continue to be enforced.
            raise HTTPException(
                status_code=429,
                detail="too many distinct rate-limit identities",
                headers={"Retry-After": "60"},
            )

        start, count, stored_window = windows.get(key, (now, 0, window_seconds))
        if stored_window != window_seconds:
            start, count, stored_window = now, 0, window_seconds
        if now - start >= window_seconds:
            start, count = now, 0
        count += 1
        windows[key] = (start, count, stored_window)

        if count > limit:
            retry_after = max(1, int(window_seconds - (now - start)) + 1)
            raise HTTPException(
                status_code=429,
                detail="too many requests, slow down",
                headers={"Retry-After": str(retry_after)},
            )


def client_ip(request: Request) -> str:
    """Peer address of the request (use a trusted proxy header if behind one)."""
    return request.client.host if request.client else "unknown"
