"""持久流量聚合、管理员趋势和成员空间统计。"""

from datetime import datetime, timedelta, timezone
import queue
import threading

import pytest
from sqlalchemy import select, text

from conftest import FAKE_PNG, auth, login, new_user

from app.core.database import SessionLocal, engine
from app.models import ApiKey, TrafficDaily, User
from app.services.traffic import (
    _prune_expired_traffic,
    flush_traffic,
    record_traffic,
    shutdown_traffic_recorder,
)


def test_traffic_counts_streamed_bytes_routes_users_and_api_keys(client):
    username, token = new_user(client)
    created = client.post(
        "/api/keys", headers=auth(token), json={"name": "traffic-key"}
    ).json()
    key_headers = {"X-API-Key": created["key"]}

    uploaded = client.post(
        "/api/upload",
        headers=key_headers,
        files={"file": ("traffic.png", FAKE_PNG, "image/png")},
    )
    assert uploaded.status_code == 201
    code = uploaded.json()["code"]
    assert client.get(f"/i/{code}").content == FAKE_PNG
    assert client.get(f"/api/media/{code}", headers=key_headers).status_code == 200

    admin_token = login(client, "admin", "admin-pass")
    report = client.get("/api/admin/traffic-stats?days=7", headers=auth(admin_token))
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["days"] == 7
    assert len(body["daily"]) == 7
    assert body["summary"]["request_count"] >= 2
    assert body["summary"]["total_bytes"] == (
        body["summary"]["request_bytes"] + body["summary"]["response_bytes"]
    )

    routes = {(item["route"], item["method"]): item for item in body["routes"]}
    assert ("/api/upload", "POST") in routes
    assert ("/api/media/{code}", "GET") in routes
    assert all(code not in item["route"] for item in body["routes"])
    assert all("?" not in item["route"] for item in body["routes"])

    key_usage = next(item for item in body["api_keys"] if item["key_prefix"] == created["key_prefix"])
    assert key_usage["key_name"] == "traffic-key"
    assert key_usage["username"] == username
    assert key_usage["request_count"] >= 2

    member = next(item for item in body["members"] if item["username"] == username)
    assert member["image_bytes"] == len(FAKE_PNG)
    assert member["video_bytes"] == 0
    assert member["storage_bytes"] == len(FAKE_PNG)
    assert member["total_usage_bytes"] >= member["storage_bytes"]
    assert member["request_count"] >= 2


def test_admin_dashboard_metrics_only_count_api_key_requests(client):
    """JWT page activity must not change the Key-only dashboard metrics."""
    username, token = new_user(client)
    created = client.post(
        "/api/keys", headers=auth(token), json={"name": "dashboard-key-only"}
    ).json()
    key_headers = {"X-API-Key": created["key"]}
    admin_token = login(client, "admin", "admin-pass")

    before = client.get(
        "/api/admin/traffic-stats?days=7", headers=auth(admin_token)
    ).json()

    # These are the same JWT-authenticated requests the management UI makes.
    for _ in range(3):
        assert client.get("/api/images", headers=auth(token)).status_code == 200
    for _ in range(2):
        assert client.get("/api/images", headers=key_headers).status_code == 200

    after_response = client.get(
        "/api/admin/traffic-stats?days=7", headers=auth(admin_token)
    )
    assert after_response.status_code == 200, after_response.text
    after = after_response.json()

    assert after["summary"]["request_count"] - before["summary"]["request_count"] == 2

    before_daily = {item["date"]: item["request_count"] for item in before["daily"]}
    after_daily = {item["date"]: item["request_count"] for item in after["daily"]}
    assert sum(after_daily.values()) - sum(before_daily.values()) == 2

    def route_count(report):
        return next(
            (
                item["request_count"]
                for item in report["routes"]
                if item["route"] == "/api/images" and item["method"] == "GET"
            ),
            0,
        )

    assert route_count(after) - route_count(before) == 2

    def key_count(report):
        return next(
            (
                item["request_count"]
                for item in report["api_keys"]
                if item["api_key_id"] == created["id"]
            ),
            0,
        )

    assert key_count(after) - key_count(before) == 2
    member = next(item for item in after["members"] if item["username"] == username)
    before_member = next(item for item in before["members"] if item["username"] == username)
    assert member["request_count"] - before_member["request_count"] == 2


@pytest.mark.parametrize("replacement_mode", ["revoke", "rotate"])
def test_revoked_or_rotated_key_history_is_never_relabelled_or_merged(
    client, replacement_mode
):
    """A retained aggregate keeps its retired identity after key replacement."""
    username, token = new_user(client)
    old = client.post(
        "/api/keys",
        headers=auth(token),
        json={"name": f"old-{replacement_mode}"},
    ).json()
    old_headers = {"X-API-Key": old["key"]}
    assert client.get("/api/auth/me", headers=old_headers).status_code == 200
    assert flush_traffic()

    if replacement_mode == "rotate":
        response = client.post(f"/api/keys/{old['id']}/rotate", headers=auth(token))
        assert response.status_code == 200, response.text
        new = response.json()
    else:
        assert client.delete(f"/api/keys/{old['id']}", headers=auth(token)).status_code == 204
        response = client.post(
            "/api/keys",
            headers=auth(token),
            json={"name": "new-after-revoke"},
        )
        assert response.status_code == 201, response.text
        new = response.json()

    assert new["id"] > old["id"]
    assert new["id"] != old["id"]
    assert client.get("/api/auth/me", headers={"X-API-Key": new["key"]}).status_code == 200
    assert flush_traffic()

    admin_token = login(client, "admin", "admin-pass")
    report = client.get("/api/admin/traffic-stats?days=7", headers=auth(admin_token))
    assert report.status_code == 200, report.text
    points = {point["api_key_id"]: point for point in report.json()["api_keys"]}
    assert old["id"] in points
    assert new["id"] in points
    assert points[old["id"]]["key_name"] is None
    assert points[old["id"]]["key_prefix"] is None
    assert points[old["id"]]["username"] == username
    assert points[new["id"]]["key_name"] == new["name"]
    assert points[new["id"]]["key_prefix"] == new["key_prefix"]
    assert points[old["id"]]["request_count"] >= 1
    assert points[new["id"]]["request_count"] >= 1

    with SessionLocal() as db:
        historical_ids = set(
            db.execute(
                select(TrafficDaily.api_key_id).where(
                    TrafficDaily.route == "/api/auth/me",
                    TrafficDaily.api_key_id.in_((old["id"], new["id"])),
                )
            ).scalars()
        )
    assert historical_ids == {old["id"], new["id"]}


def test_request_completed_before_revoke_keeps_retired_key_dimension(client, monkeypatch):
    import app.services.traffic as traffic

    _, token = new_user(client)
    created = client.post(
        "/api/keys", headers=auth(token), json={"name": "retired-before-flush"}
    ).json()
    assert flush_traffic()

    original_start = traffic._start_worker
    original_put_nowait = traffic._queue.put_nowait
    queued = []
    monkeypatch.setattr(traffic, "_start_worker", lambda: None)
    monkeypatch.setattr(traffic._queue, "put_nowait", queued.append)
    assert client.get("/api/auth/me", headers={"X-API-Key": created["key"]}).status_code == 200
    assert len(queued) == 1
    monkeypatch.setattr(traffic, "_start_worker", original_start)
    monkeypatch.setattr(traffic._queue, "put_nowait", original_put_nowait)
    assert client.delete(f"/api/keys/{created['id']}", headers=auth(token)).status_code == 204

    traffic._queue.put_nowait(queued[0])
    assert flush_traffic()
    with SessionLocal() as db:
        retained = db.scalar(
            select(TrafficDaily).where(
                TrafficDaily.api_key_id == created["id"],
                TrafficDaily.route == "/api/auth/me",
            )
        )
        assert retained is not None


def test_admin_stats_exposes_transfer_totals(client):
    admin_token = login(client, "admin", "admin-pass")
    client.get("/healthz")  # deliberately excluded from traffic accounting
    _, token = new_user(client)
    client.get("/api/auth/me", headers=auth(token))
    response = client.get("/api/admin/stats", headers=auth(admin_token))
    assert response.status_code == 200
    body = response.json()
    assert body["traffic_request_count"] >= 1
    assert body["traffic_total_bytes"] == (
        body["traffic_request_bytes"] + body["traffic_response_bytes"]
    )


def test_telemetry_write_failure_never_breaks_main_request(client, monkeypatch):
    import app.services.traffic as traffic

    original = traffic._commit_batch

    def fail(_events):
        raise OSError("simulated telemetry disk failure")

    monkeypatch.setattr(traffic, "_commit_batch", fail)
    response = client.get("/api/not-a-real-route")
    assert response.status_code == 404
    assert not flush_traffic(timeout=0.2)

    # Failed batches are retained, not silently acknowledged or discarded.
    monkeypatch.setattr(traffic, "_commit_batch", original)
    assert flush_traffic()


def test_unknown_http_methods_share_one_bounded_dimension(client):
    """Client-controlled HTTP tokens cannot create unbounded aggregate rows."""
    for method in ("A0000001", "A0000002", "CUSTOM", "TRACE"):
        assert client.request(method, "/api/not-a-real-route").status_code in (404, 405)
    assert flush_traffic()

    with SessionLocal() as db:
        rows = db.execute(
            select(TrafficDaily).where(TrafficDaily.method == "OTHER")
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].request_count >= 4


def test_retention_failure_after_commit_does_not_double_count(monkeypatch):
    import app.services.traffic as traffic

    calls = 0

    def fail_once():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated retention failure")

    monkeypatch.setattr(traffic, "_prune_expired_traffic", fail_once)
    route = "/api/retention-must-not-replay"
    record_traffic(
        user_id=None,
        api_key_id=None,
        route=route,
        method="GET",
        status_code=200,
        request_bytes=1,
        response_bytes=2,
    )
    assert flush_traffic()

    with SessionLocal() as db:
        row = db.scalar(select(TrafficDaily).where(TrafficDaily.route == route))
        assert row is not None
        assert row.request_count == 1
        assert row.request_bytes == 1
        assert row.response_bytes == 2


def test_admin_traffic_snapshots_return_503_when_flush_cannot_complete(client, monkeypatch):
    from app.api.routes import admin as admin_routes

    monkeypatch.setattr(admin_routes, "flush_traffic", lambda: False)
    admin_token = login(client, "admin", "admin-pass")
    for path in ("/api/admin/stats", "/api/admin/traffic-stats"):
        response = client.get(path, headers=auth(admin_token))
        assert response.status_code == 503
        assert response.json()["detail"] == "traffic statistics are temporarily unavailable"


def test_queue_overflow_is_reported_without_disabling_management_stats(client, monkeypatch):
    """A completed flush can be honest about earlier, unrecoverable queue loss."""
    import app.services.traffic as traffic

    assert traffic.flush_traffic()
    monkeypatch.setattr(traffic, "_dropped_events", 0)

    def reject_enqueue(_event):
        raise queue.Full

    with monkeypatch.context() as scoped:
        scoped.setattr(traffic._queue, "put_nowait", reject_enqueue)
        threads = [
            threading.Thread(
                target=traffic.record_traffic,
                kwargs={
                    "user_id": None,
                    "api_key_id": None,
                    "route": "/api/saturated-telemetry",
                    "method": "GET",
                    "status_code": 200,
                    "request_bytes": 0,
                    "response_bytes": 1,
                },
            )
            for _ in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    complete, dropped = traffic.telemetry_integrity_status()
    assert complete is False
    assert dropped == 8
    assert traffic.flush_traffic()

    admin_token = login(client, "admin", "admin-pass")
    for path in ("/api/admin/stats", "/api/admin/traffic-stats"):
        response = client.get(path, headers=auth(admin_token))
        assert response.status_code == 200, response.text
        assert response.json()["telemetry_complete"] is False
        assert response.json()["telemetry_dropped_events"] == 8


def test_shutdown_uses_one_deadline_and_warns_when_flush_or_worker_stalls(monkeypatch, caplog):
    import logging
    import time
    import app.services.traffic as traffic

    traffic.shutdown_traffic_recorder()

    class DummyQueue:
        def __init__(self):
            self.timeouts = []

        def put(self, _item, timeout):
            self.timeouts.append(timeout)

    class DummyWorker:
        def __init__(self):
            self.join_timeout = None

        def is_alive(self):
            return True

        def join(self, timeout):
            self.join_timeout = timeout

    dummy_queue = DummyQueue()
    dummy_worker = DummyWorker()
    flush_timeouts = []

    def stalled_flush(timeout):
        flush_timeouts.append(timeout)
        time.sleep(0.02)
        return False

    monkeypatch.setattr(traffic, "_queue", dummy_queue)
    monkeypatch.setattr(traffic, "_worker", dummy_worker)
    monkeypatch.setattr(traffic, "flush_traffic", stalled_flush)
    with caplog.at_level(logging.WARNING, logger=traffic.__name__):
        traffic.shutdown_traffic_recorder(timeout=0.05)

    assert flush_timeouts and 0 < flush_timeouts[0] <= 0.05
    assert dummy_queue.timeouts and dummy_queue.timeouts[0] < flush_timeouts[0]
    assert dummy_worker.join_timeout is not None
    assert dummy_worker.join_timeout <= dummy_queue.timeouts[0]
    assert "shutdown flush did not complete" in caplog.text
    assert "worker did not stop" in caplog.text


def test_flush_uses_one_timeout_budget_for_enqueue_and_barrier(monkeypatch):
    import app.services.traffic as traffic

    now = 100.0
    put_timeouts = []
    wait_timeouts = []

    class DummyQueue:
        def put(self, _item, timeout):
            nonlocal now
            put_timeouts.append(timeout)
            now += 0.75

    class DummyEvent:
        def wait(self, timeout):
            wait_timeouts.append(timeout)
            return False

    monkeypatch.setattr(traffic, "_start_worker", lambda: None)
    monkeypatch.setattr(traffic, "_queue", DummyQueue())
    monkeypatch.setattr(traffic.threading, "Event", DummyEvent)
    monkeypatch.setattr(traffic.time, "monotonic", lambda: now)

    assert traffic.flush_traffic(timeout=2.0) is False
    assert put_timeouts == [2.0]
    assert wait_timeouts == [pytest.approx(1.25)]


def test_traffic_table_has_no_foreign_keys_and_chinese_orm_comments(client):
    flush_traffic()
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_list(traffic_daily)")).all() == []
    assert all(
        column.comment and any("\u4e00" <= char <= "\u9fff" for char in column.comment)
        for column in TrafficDaily.__table__.columns
    )


def test_traffic_days_bounds_and_non_admin_denied(client):
    _, token = new_user(client)
    assert client.get("/api/admin/traffic-stats", headers=auth(token)).status_code == 403
    admin_token = login(client, "admin", "admin-pass")
    assert client.get("/api/admin/traffic-stats?days=0", headers=auth(admin_token)).status_code == 422
    assert client.get("/api/admin/traffic-stats?days=366", headers=auth(admin_token)).status_code == 422


def test_shutdown_flushes_and_recorder_restarts(client):
    _, token = new_user(client)
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    shutdown_traffic_recorder()
    # A new request starts a fresh writer; this also proves shutdown did not
    # leave a dead worker reference or lose earlier queued writes.
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200
    assert flush_traffic()


def test_user_deletion_explicitly_removes_no_fk_traffic_history(client):
    _, token = new_user(client)
    user_id = client.get("/api/auth/me", headers=auth(token)).json()["id"]
    assert flush_traffic()
    with SessionLocal() as db:
        assert db.scalar(
            select(TrafficDaily.id).where(TrafficDaily.user_id == user_id).limit(1)
        ) is not None

    admin_token = login(client, "admin", "admin-pass")
    assert client.delete(
        f"/api/admin/users/{user_id}", headers=auth(admin_token)
    ).status_code == 204
    assert flush_traffic()
    with SessionLocal() as db:
        assert db.scalar(
            select(TrafficDaily.id).where(TrafficDaily.user_id == user_id).limit(1)
        ) is None

    # Simulate a response that authenticated before deletion but reached the
    # asynchronous writer only afterwards. It must be anonymized, not recreate
    # the deleted user/key dimension.
    record_traffic(
        user_id=user_id,
        api_key_id=987654321,
        route="/api/auth/me",
        method="GET",
        status_code=200,
        request_bytes=0,
        response_bytes=12,
    )
    assert flush_traffic()
    with SessionLocal() as db:
        assert db.scalar(
            select(TrafficDaily.id).where(TrafficDaily.user_id == user_id).limit(1)
        ) is None
        anonymous = db.execute(
            select(TrafficDaily).where(
                TrafficDaily.user_id == 0,
                TrafficDaily.api_key_id == 0,
                TrafficDaily.route == "/api/auth/me",
            )
        ).scalars().all()
        assert anonymous


def test_retention_prunes_old_daily_aggregates(client, monkeypatch):
    import app.services.traffic as traffic

    monkeypatch.setattr(traffic.settings, "traffic_retention_days", 30)
    old_day = datetime.now(timezone.utc).date() - timedelta(days=31)
    recent_day = datetime.now(timezone.utc).date() - timedelta(days=29)
    with SessionLocal() as db:
        db.add_all([
            TrafficDaily(
                day=old_day, user_id=0, api_key_id=0, route="/api/old", method="GET",
                request_count=1, error_count=0, request_bytes=0, response_bytes=1,
            ),
            TrafficDaily(
                day=recent_day, user_id=0, api_key_id=0, route="/api/recent", method="GET",
                request_count=1, error_count=0, request_bytes=0, response_bytes=1,
            ),
        ])
        db.commit()
    _prune_expired_traffic(force=True)
    with SessionLocal() as db:
        assert db.scalar(select(TrafficDaily.id).where(TrafficDaily.route == "/api/old")) is None
        assert db.scalar(select(TrafficDaily.id).where(TrafficDaily.route == "/api/recent")) is not None


def test_late_deleted_identity_event_is_anonymized(client):
    """Late events cannot revive deleted tenant/key dimensions."""
    _, old_token = new_user(client)
    old_user = client.get("/api/auth/me", headers=auth(old_token)).json()
    old_key_payload = client.post("/api/keys", headers=auth(old_token)).json()
    with SessionLocal() as db:
        old_user_row = db.get(User, old_user["id"])
        old_key_row = db.scalar(
            select(ApiKey).where(ApiKey.key_prefix == old_key_payload["key_prefix"])
        )
        old_user_stamp = old_user_row.created_at.isoformat()
        old_key_id = old_key_row.id
        old_key_stamp = old_key_row.created_at.isoformat()

    admin_token = login(client, "admin", "admin-pass")
    assert client.delete(
        f"/api/admin/users/{old_user['id']}", headers=auth(admin_token)
    ).status_code == 204
    replacement_name = f"replacement-{old_user['id']}"
    replacement = client.post(
        "/api/admin/users",
        headers=auth(admin_token),
        json={"username": replacement_name, "password": "pass123", "role": "user"},
    )
    assert replacement.status_code == 201
    assert replacement.json()["id"] > old_user["id"]
    replacement_token = login(client, replacement_name)
    replacement_key = client.post("/api/keys", headers=auth(replacement_token)).json()
    with SessionLocal() as db:
        replacement_key_row = db.scalar(
            select(ApiKey).where(ApiKey.key_prefix == replacement_key["key_prefix"])
        )
        assert replacement_key_row.id > old_key_id

    record_traffic(
        user_id=old_user["id"],
        api_key_id=old_key_id,
        user_created_at=old_user_stamp,
        api_key_created_at=old_key_stamp,
        route="/api/late-reused-identity",
        method="GET",
        status_code=200,
        request_bytes=1,
        response_bytes=2,
    )
    assert flush_traffic()
    with SessionLocal() as db:
        late = db.scalar(
            select(TrafficDaily).where(TrafficDaily.route == "/api/late-reused-identity")
        )
        assert late is not None
        assert late.user_id == 0
        assert late.api_key_id == 0


def test_identity_check_and_upsert_share_lifecycle_lease_with_user_delete(client, monkeypatch):
    import app.services.traffic as traffic

    _, token = new_user(client)
    user_id = client.get("/api/auth/me", headers=auth(token)).json()["id"]
    with SessionLocal() as db:
        user_stamp = db.get(User, user_id).created_at.isoformat()

    entered = threading.Event()
    release = threading.Event()
    original = traffic._commit_batch_under_lease

    def gated(events):
        # _commit_batch has already acquired the lifecycle lease here.
        entered.set()
        assert release.wait(3)
        return original(events)

    monkeypatch.setattr(traffic, "_commit_batch_under_lease", gated)
    record_traffic(
        user_id=user_id,
        api_key_id=0,
        user_created_at=user_stamp,
        route="/api/lifecycle-race",
        method="GET",
        status_code=200,
        request_bytes=0,
        response_bytes=1,
    )
    assert entered.wait(2)

    admin_token = login(client, "admin", "admin-pass")
    result = {}
    finished = threading.Event()

    def delete_target():
        result["response"] = client.delete(
            f"/api/admin/users/{user_id}", headers=auth(admin_token)
        )
        finished.set()

    thread = threading.Thread(target=delete_target)
    thread.start()
    assert not finished.wait(0.2), "delete unexpectedly bypassed traffic lifecycle lease"
    release.set()
    assert finished.wait(5)
    thread.join(timeout=1)
    assert result["response"].status_code == 204
    assert flush_traffic()
    with SessionLocal() as db:
        assert db.scalar(
            select(TrafficDaily.id).where(TrafficDaily.user_id == user_id).limit(1)
        ) is None
