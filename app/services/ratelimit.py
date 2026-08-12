"""In-process fixed-window rate limiter.

Suited to the single-container deployment. For horizontal scaling, replace
this with a shared store (e.g. Redis) — only the ``check_rate_limit`` call
sites need to change.
"""

import time
from threading import Lock

from fastapi import HTTPException, Request

# key -> (window_start, count)
_WINDOWS: dict[str, tuple[float, int]] = {}
_LOCK = Lock()
_MAX_WINDOWS = 10_000
_PRUNE_AFTER = 3600  # seconds


def _prune(now: float) -> None:
    stale = [k for k, (start, _) in _WINDOWS.items() if now - start >= _PRUNE_AFTER]
    for k in stale:
        del _WINDOWS[k]


def check_rate_limit(key: str, limit: int, window_seconds: int = 60) -> None:
    """Raise HTTP 429 when ``key`` exceeds ``limit`` requests per window."""
    if limit <= 0:
        return
    now = time.monotonic()
    with _LOCK:
        _prune(now)
        if len(_WINDOWS) >= _MAX_WINDOWS:
            _WINDOWS.clear()

        start, count = _WINDOWS.get(key, (now, 0))
        if now - start >= window_seconds:
            start, count = now, 0
        count += 1
        _WINDOWS[key] = (start, count)

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
