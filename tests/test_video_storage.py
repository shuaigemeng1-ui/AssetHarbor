"""Container detection, schema migration and cleanup invariants."""

from __future__ import annotations

import asyncio
import hashlib
import threading
import time
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text

from conftest import MP4_HEADER


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (MP4_HEADER, ("video/mp4", "mp4")),
        (b"\x00\x00\x00\x18ftypM4V \x00\x00\x00\x00M4V mp42", ("video/x-m4v", "m4v")),
        (b"\x00\x00\x00\x18ftypqt  \x00\x00\x00\x00qt  mp42", ("video/quicktime", "mov")),
        (b"\x00\x00\x00\x18ftyp3gp6\x00\x00\x00\x003gp6isom", ("video/3gpp", "3gp")),
        (b"\x1a\x45\xdf\xa3\x00webm\x00", ("video/webm", "webm")),
        (b"\x1a\x45\xdf\xa3\x00matroska\x00", ("video/x-matroska", "mkv")),
        (b"RIFF\x04\x00\x00\x00AVI ", ("video/x-msvideo", "avi")),
        (b"\x00\x00\x01\xba" + b"\0" * 8, ("video/mpeg", "mpg")),
        (b"\x47" + b"\0" * 187 + b"\x47", ("video/mp2t", "ts")),
        (b"OggS\0\0theora\0", ("video/ogg", "ogv")),
        (b"FLV\x01\x01", ("video/x-flv", "flv")),
        (bytes.fromhex("3026b2758e66cf11a6d900aa0062ce6c"), ("video/x-ms-wmv", "wmv")),
    ],
)
def test_detect_supported_video_containers(data, expected):
    from app.services.videos import detect_video_type

    assert detect_video_type(data) == expected


@pytest.mark.parametrize(
    "data",
    [
        b"not video",
        b"\x89PNG\r\n\x1a\n",
        b"\x00\x00\x00\x18ftypavif\x00\x00\x00\x00avifisom",
        b"FLV\x01\x00",
        b"OggS\0\0vorbis\0",
    ],
)
def test_detect_rejects_non_video_and_ambiguous_containers(data):
    from app.services.videos import detect_video_type

    assert detect_video_type(data) is None


def test_upload_tables_have_unique_part_key_and_no_foreign_keys(client):
    from app.core.database import engine

    with engine.connect() as conn:
        for table in ("upload_sessions", "upload_parts"):
            assert conn.execute(text(f"PRAGMA foreign_key_list({table})")).all() == []
        indexes = conn.execute(text("PRAGMA index_list(upload_parts)")).all()
        assert any(row[2] for row in indexes)  # at least one UNIQUE index
        image_cols = {row[1]: row for row in conn.execute(text("PRAGMA table_info(images)"))}
        assert image_cols["media_kind"][4] == "'image'"


def test_idempotent_migration_preserves_legacy_image_and_adds_no_upload_fks(tmp_path, monkeypatch):
    from app.core import database

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as conn:
        conn.execute(text("CREATE TABLE images (id INTEGER PRIMARY KEY, code VARCHAR(32))"))
        conn.execute(text("INSERT INTO images (id, code) VALUES (1, 'legacy')"))
    monkeypatch.setattr(database, "engine", legacy_engine)
    database._migrate()
    database._migrate()
    with legacy_engine.connect() as conn:
        row = conn.execute(text("SELECT id, code, media_kind FROM images")).one()
        assert tuple(row) == (1, "legacy", "image")
        assert conn.execute(text("PRAGMA foreign_key_list(upload_sessions)")).all() == []
        assert conn.execute(text("PRAGMA foreign_key_list(upload_parts)")).all() == []


def test_sqlite_wal_and_busy_timeout_are_enabled(client):
    from app.core.database import engine
    from app.core.config import settings

    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar_one().lower() == "wal"
        assert conn.execute(text("PRAGMA busy_timeout")).scalar_one() == settings.sqlite_busy_timeout_ms


def test_periodic_cleanup_removes_expired_rows_and_orphan_directories(client):
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services.videos import _now, cleanup_expired_uploads
    from conftest import init_video, new_user

    data = MP4_HEADER + b"cleanup"
    _, token = new_user(client)
    upload_id = init_video(client, token, data).json()["upload_id"]
    orphan = settings.uploads_dir / "orphan-session"
    orphan.mkdir(parents=True, exist_ok=True)
    (orphan / "part.tmp").write_bytes(b"orphan")
    with SessionLocal() as db:
        row = db.get(UploadSession, upload_id)
        row.expires_at = _now() - timedelta(seconds=1)
        db.commit()
    assert cleanup_expired_uploads() >= 1
    assert not (settings.uploads_dir / upload_id).exists()
    assert not orphan.exists()


def test_inbound_upload_gate_is_reclaimed_after_all_users_release():
    from app.services import videos

    upload_id = "gate-reclamation-test"
    first = videos._lease_inbound_upload_gate(upload_id)
    second = videos._lease_inbound_upload_gate(upload_id)
    assert first is second

    videos._release_inbound_upload_gate(upload_id, first)
    assert upload_id in videos._inbound_upload_gates
    videos._release_inbound_upload_gate(upload_id, second)
    assert upload_id not in videos._inbound_upload_gates


def test_upload_lock_is_identity_stable_and_reclaimed_at_zero_users():
    from app.services import videos

    upload_id = "lock-reclamation-test"
    with videos._leased_upload_lock(upload_id) as first:
        assert videos._upload_locks[upload_id] is first
        with videos._leased_upload_lock(upload_id) as second:
            assert second is first
        assert videos._upload_locks[upload_id] is first
    assert upload_id not in videos._upload_locks
    assert upload_id not in videos._upload_lock_users


def test_sparse_hole_write_reserves_two_chunks_of_peak_growth():
    from app.services.videos import _part_peak_growth

    # Filling an existing sparse hole does not increase st_size, but may still
    # allocate the entire target chunk in addition to the temporary chunk.
    assert _part_peak_growth(expected_size=8, offset=0, current_file_size=128) == 16
    # Extending beyond EOF reserves the larger logical extension as well.
    assert _part_peak_growth(expected_size=8, offset=200, current_file_size=128) == 88


def test_cancel_waits_for_the_inbound_upload_gate(client):
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services import videos
    from conftest import init_video, new_user

    _, token = new_user(client)
    upload_id = init_video(client, token, MP4_HEADER + b"gate").json()["upload_id"]
    gate = videos._lease_inbound_upload_gate(upload_id)
    gate.acquire()
    finished = threading.Event()
    failures: list[BaseException] = []

    def cancel_in_worker() -> None:
        try:
            with SessionLocal() as db:
                upload = db.get(UploadSession, upload_id)
                assert upload is not None
                videos.cancel_upload_session(db, upload)
        except BaseException as exc:  # surface worker failures in the test thread
            failures.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=cancel_in_worker, daemon=True)
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with videos._inbound_gate_guard:
                if videos._inbound_gate_users.get(upload_id) == 2:
                    break
            time.sleep(0.005)
        with videos._inbound_gate_guard:
            assert videos._inbound_gate_users.get(upload_id) == 2
        assert not finished.is_set()
    finally:
        gate.release()
        videos._release_inbound_upload_gate(upload_id, gate)
    worker.join(timeout=2)
    assert finished.is_set()
    assert failures == []
    with SessionLocal() as db:
        assert db.get(UploadSession, upload_id) is None


def test_already_authorized_put_cannot_recreate_a_canceled_session(client):
    from fastapi import HTTPException

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services import videos
    from conftest import init_video, new_user

    data = MP4_HEADER + b"stale-put"
    _, token = new_user(client)
    upload_id = init_video(client, token, data).json()["upload_id"]

    class BodyRequest:
        headers = {"content-length": str(len(data))}

        async def stream(self):
            yield data

    with SessionLocal() as stale_db:
        stale_upload = stale_db.get(UploadSession, upload_id)
        assert stale_upload is not None
        with SessionLocal() as cancel_db:
            current = cancel_db.get(UploadSession, upload_id)
            assert current is not None
            videos.cancel_upload_session(cancel_db, current)

        with pytest.raises(HTTPException) as error:
            asyncio.run(
                videos.store_upload_part(
                    stale_db,
                    stale_upload,
                    0,
                    BodyRequest(),
                    f"bytes 0-{len(data) - 1}/{len(data)}",
                    hashlib.sha256(data).hexdigest(),
                )
            )
    assert error.value.status_code == 404
    assert not (settings.uploads_dir / upload_id).exists()


def test_orphan_sweep_rechecks_database_before_removing_directory(client):
    from app.core.config import settings
    from app.services.videos import _cleanup_upload_directory
    from conftest import init_video, new_user

    data = MP4_HEADER + b"fresh-session"
    _, token = new_user(client)
    upload_id = init_video(client, token, data).json()["upload_id"]
    directory = settings.uploads_dir / upload_id

    # Simulate a directory absent from an earlier caller snapshot: the helper
    # must trust its fresh query while holding the same gate used by PUT/delete.
    assert _cleanup_upload_directory(directory, time.time()) is False
    assert directory.is_dir()
