"""Image storage compensation and operational readiness checks."""

import errno
import uuid
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from app.core import database
from app.core.config import settings
from app.models import Image
from app.services import images, videos
from conftest import login, register, upload


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
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
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
