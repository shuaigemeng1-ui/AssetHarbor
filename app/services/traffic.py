"""低开销、失败隔离的持久化 API 流量聚合器。"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..core.database import SessionLocal
from ..core.config import settings
from ..models.api_key import ApiKey
from ..models.traffic import TrafficDaily
from ..models.user import User
from .library import library_lifecycle_lease

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TrafficEvent:
    day: date
    user_id: int
    api_key_id: int
    user_created_at: str | None
    api_key_created_at: str | None
    route: str
    method: str
    request_count: int = 1
    error_count: int = 0
    request_bytes: int = 0
    response_bytes: int = 0


@dataclass(slots=True)
class _Barrier:
    done: threading.Event


_STOP = object()
_QUEUE_LIMIT = 100_000
_BATCH_LIMIT = 512
_TRACKED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})
_queue: queue.Queue[TrafficEvent | _Barrier | object] = queue.Queue(maxsize=_QUEUE_LIMIT)
_state_lock = threading.Lock()
_dropped_events_lock = threading.Lock()
_worker: threading.Thread | None = None
_last_prune_day: date | None = None
_dropped_events = 0
_last_drop_log_at = 0.0
_last_writer_error_log_at = 0.0
_writer_failure_streak = 0
_next_prune_retry_at = 0.0


def _record_dropped_event() -> None:
    """Atomically retain process-lifetime evidence of telemetry data loss."""
    global _dropped_events, _last_drop_log_at
    with _dropped_events_lock:
        _dropped_events += 1
        dropped = _dropped_events
        now = time.monotonic()
        should_log = dropped == 1 or now - _last_drop_log_at >= 60
        if should_log:
            _last_drop_log_at = now
    if should_log:
        logger.warning("traffic statistics events dropped total=%d", dropped)


def telemetry_integrity_status() -> tuple[bool, int]:
    """Return a coherent, thread-safe snapshot for management responses."""
    with _dropped_events_lock:
        dropped = _dropped_events
    return dropped == 0, dropped


def _prune_expired_traffic(*, force: bool = False) -> None:
    """Delete expired daily aggregates at most once per UTC day."""
    global _last_prune_day, _next_prune_retry_at
    today = datetime.now(timezone.utc).date()
    if not force and _last_prune_day == today:
        return
    if not force and time.monotonic() < _next_prune_retry_at:
        return
    cutoff = today - timedelta(days=settings.traffic_retention_days - 1)
    with SessionLocal() as db:
        db.execute(delete(TrafficDaily).where(TrafficDaily.day < cutoff))
        db.commit()
    _last_prune_day = today
    _next_prune_retry_at = 0.0


def _start_worker() -> None:
    global _worker
    with _state_lock:
        if _worker is not None and _worker.is_alive():
            return
        _worker = threading.Thread(target=_worker_loop, name="oss-traffic-writer", daemon=True)
        _worker.start()


def record_traffic(
    *,
    user_id: int | None,
    api_key_id: int | None,
    user_created_at: str | None = None,
    api_key_created_at: str | None = None,
    route: str,
    method: str,
    status_code: int,
    request_bytes: int,
    response_bytes: int,
) -> None:
    """Queue one aggregate event without blocking or failing the HTTP request."""
    normalized_method = (method or "").upper()
    if normalized_method not in _TRACKED_METHODS:
        normalized_method = "OTHER"
    event = TrafficEvent(
        day=datetime.now(timezone.utc).date(),
        user_id=max(0, int(user_id or 0)),
        api_key_id=max(0, int(api_key_id or 0)),
        user_created_at=user_created_at,
        api_key_created_at=api_key_created_at,
        route=(route or "unknown")[:160],
        method=normalized_method,
        error_count=1 if status_code >= 400 else 0,
        request_bytes=max(0, int(request_bytes)),
        response_bytes=max(0, int(response_bytes)),
    )
    try:
        _start_worker()
        _queue.put_nowait(event)
    except Exception:
        # Telemetry must never change an API response. A bounded queue also
        # prevents traffic spikes from causing unbounded process memory growth.
        _record_dropped_event()


def flush_traffic(timeout: float = 2.0) -> bool:
    """Wait until all earlier events have been committed (admin/tests/shutdown)."""
    _start_worker()
    barrier = _Barrier(threading.Event())
    budget = max(0.0, timeout)
    deadline = time.monotonic() + budget
    try:
        _queue.put(barrier, timeout=budget)
    except queue.Full:
        return False
    remaining = min(budget, max(0.0, deadline - time.monotonic()))
    return barrier.done.wait(remaining)


def shutdown_traffic_recorder(timeout: float = 2.0) -> None:
    """Flush and stop within one deadline, warning on every incomplete step."""
    global _worker
    budget = max(0.0, timeout)
    deadline = time.monotonic() + budget

    def remaining() -> float:
        # Floating-point addition/subtraction can otherwise return a value a
        # few picoseconds above the caller's requested total timeout.
        return min(budget, max(0.0, deadline - time.monotonic()))

    if not flush_traffic(remaining()):
        logger.warning("traffic recorder shutdown flush did not complete before deadline")
    with _state_lock:
        worker = _worker
        if worker is None:
            return
        try:
            _queue.put(_STOP, timeout=remaining())
        except queue.Full:
            logger.warning("traffic recorder shutdown could not enqueue stop before deadline")
            return
    worker.join(remaining())
    with _state_lock:
        if _worker is worker and not worker.is_alive():
            _worker = None
        elif _worker is worker:
            logger.warning("traffic recorder worker did not stop before deadline")


def _commit_batch(events: list[TrafficEvent]) -> None:
    # User/key creation and deletion use this same lease. Holding it across
    # identity resolution and upsert prevents SQLite PK reuse from ever
    # attributing a late request to a newly created account.
    with library_lifecycle_lease():
        _commit_batch_under_lease(events)
    # Retention can delete many historical rows. It is independent from
    # identity attribution and must not hold the global account/media lifecycle
    # lease while SQLite performs that maintenance work.
    global _next_prune_retry_at
    try:
        _prune_expired_traffic()
    except Exception:
        now = time.monotonic()
        if now >= _next_prune_retry_at:
            logger.exception("traffic retention prune failed; retrying in 60 seconds")
        _next_prune_retry_at = now + 60


def _commit_batch_under_lease(events: list[TrafficEvent]) -> None:
    # Authentication and account deletion can race: an already authenticated
    # request may finish after its account/key has been removed. Resolve all
    # referenced identities in two batched reads and anonymize stale ones before
    # the upsert, so no late event can recreate deleted tenant identifiers.
    with SessionLocal() as db:
        # The identity check and aggregate upsert must share one SQLite writer
        # transaction. If deletion wins first we anonymize; if this transaction
        # wins first, deletion waits and then explicitly removes these rows.
        # This closes the final query/delete/upsert race without database FKs.
        db.execute(text("BEGIN IMMEDIATE"))
        user_ids = {event.user_id for event in events if event.user_id > 0}
        key_ids = {event.api_key_id for event in events if event.api_key_id > 0}
        existing_users = {
            user_id: created_at.isoformat()
            for user_id, created_at in db.execute(
                select(User.id, User.created_at).where(User.id.in_(user_ids))
            ).all()
        } if user_ids else {}
        existing_keys = {
            key_id: (user_id, created_at.isoformat())
            for key_id, user_id, created_at in db.execute(
                select(ApiKey.id, ApiKey.user_id, ApiKey.created_at).where(ApiKey.id.in_(key_ids))
            ).all()
        } if key_ids else {}
        merged: dict[tuple, TrafficEvent] = {}
        for event in events:
            user_id = (
                event.user_id
                if event.user_created_at is not None
                and existing_users.get(event.user_id) == event.user_created_at
                else 0
            )
            api_key_identity = existing_keys.get(event.api_key_id)
            api_key_id = (
                event.api_key_id
                if user_id > 0
                and event.api_key_created_at is not None
                and (
                    api_key_identity == (user_id, event.api_key_created_at)
                    # A request can finish before its Key is revoked but reach
                    # this asynchronous writer afterwards. Key IDs are now
                    # durably monotonic, so absence is a retired identity, not
                    # a replacement; retain its truthful historical dimension.
                    or api_key_identity is None
                )
                else 0
            )
            key = (event.day, user_id, api_key_id, event.route, event.method)
            previous = merged.get(key)
            if previous is None:
                merged[key] = TrafficEvent(
                    day=event.day,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    user_created_at=event.user_created_at,
                    api_key_created_at=event.api_key_created_at,
                    route=event.route,
                    method=event.method,
                    request_count=event.request_count,
                    error_count=event.error_count,
                    request_bytes=event.request_bytes,
                    response_bytes=event.response_bytes,
                )
            else:
                merged[key] = TrafficEvent(
                    day=event.day,
                    user_id=user_id,
                    api_key_id=api_key_id,
                    user_created_at=event.user_created_at,
                    api_key_created_at=event.api_key_created_at,
                    route=event.route,
                    method=event.method,
                    request_count=previous.request_count + event.request_count,
                    error_count=previous.error_count + event.error_count,
                    request_bytes=previous.request_bytes + event.request_bytes,
                    response_bytes=previous.response_bytes + event.response_bytes,
                )

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for event in merged.values():
            values = {
                "day": event.day,
                "user_id": event.user_id,
                "api_key_id": event.api_key_id,
                "route": event.route,
                "method": event.method,
                "request_count": event.request_count,
                "error_count": event.error_count,
                "request_bytes": event.request_bytes,
                "response_bytes": event.response_bytes,
                "created_at": now,
                "updated_at": now,
            }
            statement = sqlite_insert(TrafficDaily).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["day", "user_id", "api_key_id", "route", "method"],
                set_={
                    "request_count": TrafficDaily.request_count + statement.excluded.request_count,
                    "error_count": TrafficDaily.error_count + statement.excluded.error_count,
                    "request_bytes": TrafficDaily.request_bytes + statement.excluded.request_bytes,
                    "response_bytes": TrafficDaily.response_bytes + statement.excluded.response_bytes,
                    "updated_at": now,
                },
            )
            db.execute(statement)
        db.commit()


def _worker_loop() -> None:
    global _last_writer_error_log_at, _writer_failure_streak
    events: list[TrafficEvent] = []
    deferred_control: _Barrier | object | None = None
    while True:
        if deferred_control is not None:
            item = deferred_control
            deferred_control = None
        elif events:
            # A failed batch is retried before consuming later queue items, so
            # an already-enqueued barrier can never acknowledge dropped data.
            item = None
        else:
            try:
                item = _queue.get(timeout=0.25)
            except queue.Empty:
                item = None

        if isinstance(item, TrafficEvent):
            events.append(item)
            while len(events) < _BATCH_LIMIT:
                try:
                    next_item = _queue.get_nowait()
                except queue.Empty:
                    break
                if isinstance(next_item, TrafficEvent):
                    events.append(next_item)
                    continue
                # Preserve ordering for a barrier/stop encountered while
                # draining by processing it after this batch.
                item = next_item
                break

        if events:
            try:
                _commit_batch(events)
            except Exception:
                _writer_failure_streak += 1
                now = time.monotonic()
                if _writer_failure_streak == 1 or now - _last_writer_error_log_at >= 60:
                    _last_writer_error_log_at = now
                    logger.exception(
                        "traffic statistics batch write failed attempts=%d",
                        _writer_failure_streak,
                    )
                if isinstance(item, _Barrier) or item is _STOP:
                    deferred_control = item
                # Retain and retry the exact batch. Normal requests remain
                # non-blocking behind the bounded queue; flush returns false
                # when persistence cannot recover within its timeout.
                time.sleep(min(5.0, 0.1 * (2 ** min(_writer_failure_streak - 1, 6))))
                continue
            if _writer_failure_streak:
                logger.info(
                    "traffic statistics writer recovered attempts=%d",
                    _writer_failure_streak,
                )
                _writer_failure_streak = 0
            events.clear()

        if isinstance(item, _Barrier):
            item.done.set()
        elif item is _STOP:
            return
