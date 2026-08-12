"""Image storage compensation and operational readiness checks."""

import errno
import sqlite3
import threading
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.core import database
import app.main as app_main
from app.core.config import settings
from app.models import Image
from app.services import images, videos
from conftest import login, register, upload


@pytest.fixture(autouse=True)
def _clear_readyz_cache():
    """No readiness result may leak into a test that patches a probe."""
    app_main._reset_readiness_cache()
    try:
        yield
    finally:
        app_main._reset_readiness_cache()


def _image_count() -> int:
    with database.SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Image)) or 0


def _stored_media_files() -> set[Path]:
    return {path for path in settings.files_dir.rglob("*") if path.is_file()}


def _readiness_probes() -> list[Path]:
    return list(settings.data_dir.glob(".readyz-*"))


def _storage_user(client) -> str:
    username = f"storage-{uuid.uuid4().hex[:16]}"
    register(client, username)
    return login(client, username)


def test_image_upload_insufficient_space_is_507_and_leaves_no_artifacts(client, monkeypatch):
    token = _storage_user(client)
    before_count = _image_count()
    before_files = _stored_media_files()

    def reject_space(_required_bytes):
        raise videos.HTTPException(status_code=507, detail="insufficient storage space")

    monkeypatch.setattr(videos, "_reserve_write_space", reject_space)

    response = upload(client, token)

    assert response.status_code == 507
    assert response.json()["detail"] == "insufficient storage space"
    assert _image_count() == before_count
    assert _stored_media_files() == before_files
    assert not list(settings.files_dir.rglob("*.tmp"))


def test_image_enospc_is_507_and_removes_temp_file(client, monkeypatch):
    token = _storage_user(client)
    before_count = _image_count()
    before_files = _stored_media_files()

    def fail_write(_path, _data):
        raise OSError(errno.ENOSPC, "no space left on device")

    monkeypatch.setattr(Path, "write_bytes", fail_write)

    response = upload(client, token)

    assert response.status_code == 507
    assert _image_count() == before_count
    assert _stored_media_files() == before_files
    assert not list(settings.files_dir.rglob("*.tmp"))


def test_image_database_commit_failure_removes_published_file(client, monkeypatch):
    token = _storage_user(client)
    before_count = _image_count()
    before_files = _stored_media_files()
    real_commit = database.SessionLocal.class_.commit
    failed = False

    def fail_image_commit(db):
        nonlocal failed
        if not failed and any(isinstance(value, Image) for value in db.new):
            failed = True
            raise OperationalError("INSERT", {}, Exception("database or disk is full"))
        return real_commit(db)

    monkeypatch.setattr(database.SessionLocal.class_, "commit", fail_image_commit)

    response = upload(client, token)

    assert response.status_code == 507
    assert _image_count() == before_count
    assert _stored_media_files() == before_files
    assert not list(settings.files_dir.rglob("*.tmp"))


def test_readyz_checks_database_storage_and_leaves_no_probe(client):
    with database.SessionLocal() as db:
        before_users = db.execute(text("SELECT COUNT(*) FROM users")).scalar_one()

    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert _readiness_probes() == []
    with database.SessionLocal() as db:
        assert db.execute(text("SELECT COUNT(*) FROM users")).scalar_one() == before_users
        db.execute(text("BEGIN IMMEDIATE"))
        db.rollback()


def test_readyz_concurrent_requests_share_one_successful_probe(monkeypatch):
    workers = 8
    start = threading.Barrier(workers)
    database_calls = 0
    storage_calls = 0
    counter_lock = threading.Lock()

    def database_probe():
        nonlocal database_calls
        with counter_lock:
            database_calls += 1

    def storage_probe():
        nonlocal storage_calls
        with counter_lock:
            storage_calls += 1

    monkeypatch.setattr(app_main, "_probe_database_write", database_probe)
    monkeypatch.setattr(app_main, "_probe_data_directory", storage_probe)
    monkeypatch.setattr(app_main, "ensure_free_space", lambda: None)

    results = []

    def worker():
        start.wait()
        results.append(app_main.readyz())

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=3)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == workers
    assert all(result.status == "ready" for result in results)
    assert database_calls == 1
    assert storage_calls == 1


def test_readyz_caches_failure_without_repeating_probe(client, monkeypatch):
    calls = 0

    def fail_database_probe():
        nonlocal calls
        calls += 1
        raise OperationalError("BEGIN IMMEDIATE", {}, Exception("database unavailable"))

    monkeypatch.setattr(app_main, "_probe_database_write", fail_database_probe)

    first = client.get("/readyz")
    second = client.get("/readyz")

    assert first.status_code == second.status_code == 503
    assert first.json()["detail"] == second.json()["detail"] == "database is not ready"
    assert calls == 1


def test_readyz_rejects_sqlite_query_only_mode(client, monkeypatch, tmp_path):
    db_path = tmp_path / "query-only.db"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
        connection.commit()
    finally:
        connection.close()

    query_only_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(query_only_engine, "connect")
    def _enable_query_only(dbapi_connection, _connection_record):
        dbapi_connection.execute("PRAGMA query_only=ON")

    query_only_sessions = sessionmaker(bind=query_only_engine)
    monkeypatch.setattr("app.main.SessionLocal", query_only_sessions)
    try:
        response = client.get("/readyz")
    finally:
        query_only_engine.dispose()

    assert response.status_code == 503
    assert response.json()["detail"] == "database is not ready"
    assert _readiness_probes() == []


def test_readyz_database_failure_returns_503(client, monkeypatch):
    class BrokenSession:
        def __enter__(self):
            raise OperationalError("SELECT 1", {}, Exception("database unavailable"))

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.main.SessionLocal", BrokenSession)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"] == "database is not ready"
    assert _readiness_probes() == []


def test_readyz_write_probe_failure_returns_503_without_probe(client, monkeypatch):
    def fail_fsync(_descriptor):
        raise OSError(errno.EDQUOT if hasattr(errno, "EDQUOT") else errno.ENOSPC, "quota")

    monkeypatch.setattr("app.main.os.fsync", fail_fsync)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"] == "storage is not ready"
    assert _readiness_probes() == []


def test_readyz_free_space_failure_returns_503_and_removes_probe(client, monkeypatch):
    def reject_space(_required_bytes=0):
        raise videos.HTTPException(status_code=507, detail="insufficient storage space")

    monkeypatch.setattr("app.main.ensure_free_space", reject_space)

    response = client.get("/readyz")

    assert response.status_code == 503
    assert response.json()["detail"] == "storage is not ready"
    assert _readiness_probes() == []
