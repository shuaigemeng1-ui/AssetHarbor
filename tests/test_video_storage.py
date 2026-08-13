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


def test_cleanup_does_not_delete_source_being_verified(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services import videos
    from conftest import auth, init_video, new_user, put_video_part

    data = MP4_HEADER + b"cleanup-during-verification"
    _, token = new_user(client)
    initialized = init_video(client, token, data)
    assert initialized.status_code == 201, initialized.text
    upload_id = initialized.json()["upload_id"]
    assert put_video_part(
        client, token, upload_id, 0, data, 0, len(data)
    ).status_code == 200

    real_verify = videos._verify_parts_and_sha256
    hashing = threading.Event()
    release_hash = threading.Event()
    finished = threading.Event()
    outcome = {}

    def blocked_verify(path, parts):
        hashing.set()
        assert release_hash.wait(5), "test did not release hashing"
        return real_verify(path, parts)

    monkeypatch.setattr(videos, "_verify_parts_and_sha256", blocked_verify)

    def complete_worker():
        try:
            outcome["response"] = client.post(
                f"/api/video-uploads/{upload_id}/complete", headers=auth(token)
            )
        finally:
            finished.set()

    thread = threading.Thread(target=complete_worker)
    thread.start()
    assert hashing.wait(2), "completion never entered verification"
    try:
        with SessionLocal() as db:
            upload = db.get(UploadSession, upload_id)
            assert upload.status == "verifying"
            upload.expires_at = videos._now() - timedelta(seconds=1)
            db.commit()
        videos.cleanup_expired_uploads()
        assert videos.session_file(upload_id).is_file()
        with SessionLocal() as db:
            upload = db.get(UploadSession, upload_id)
            assert upload is not None and upload.status == "active"
            assert upload.expires_at > videos._now()
    finally:
        release_hash.set()

    assert finished.wait(5), "completion did not return after cleanup recovery"
    thread.join(timeout=2)
    assert outcome["response"].status_code == 409
    assert videos.session_file(upload_id).is_file()


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
                videos.cancel_upload_session_internal(db, upload)
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
    from app.models import UploadSession, User
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
            videos.cancel_upload_session_internal(cancel_db, current)

        with pytest.raises(HTTPException) as error:
            asyncio.run(
                videos.store_upload_part(
                    stale_db,
                    stale_upload,
                    stale_db.get(User, stale_upload.owner_id),
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


def test_cleanup_candidate_scan_does_not_hold_global_lifecycle_locks(client, monkeypatch):
    from app.services import videos
    from conftest import init_video, new_user

    _, token = new_user(client)
    upload_id = init_video(client, token, MP4_HEADER + b"unlocked-scan").json()[
        "upload_id"
    ]
    real_session_file = videos.session_file
    scan_entered = threading.Event()
    release_scan = threading.Event()
    cleanup_finished = threading.Event()
    failures: list[BaseException] = []

    def blocked_session_file(candidate_id):
        if candidate_id == upload_id and not scan_entered.is_set():
            scan_entered.set()
            assert release_scan.wait(5), "test did not release cleanup snapshot"
        return real_session_file(candidate_id)

    monkeypatch.setattr(videos, "session_file", blocked_session_file)

    def cleanup_worker():
        try:
            videos.cleanup_expired_uploads()
        except BaseException as exc:
            failures.append(exc)
        finally:
            cleanup_finished.set()

    worker = threading.Thread(target=cleanup_worker, daemon=True)
    worker.start()
    assert scan_entered.wait(2), "cleanup never reached its filesystem snapshot"
    try:
        assert videos._session_create_lock.acquire(timeout=0.5)
        videos._session_create_lock.release()

        lease_acquired = threading.Event()

        def lifecycle_probe():
            with videos.library_lifecycle_lease():
                lease_acquired.set()

        probe = threading.Thread(target=lifecycle_probe, daemon=True)
        probe.start()
        assert lease_acquired.wait(0.5), "cleanup snapshot held the lifecycle lease"
        probe.join(timeout=1)
    finally:
        release_scan.set()

    worker.join(timeout=5)
    assert cleanup_finished.is_set()
    assert failures == []


def test_orphan_snapshot_cannot_delete_session_created_before_fresh_check(
    client, monkeypatch
):
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services import videos
    from conftest import init_video, new_user

    fixed_id = "12345678-1234-4234-8234-123456789abc"
    directory = settings.uploads_dir / fixed_id
    directory.mkdir(parents=True, exist_ok=True)
    sweep_entered = threading.Event()
    release_sweep = threading.Event()
    cleanup_finished = threading.Event()
    failures: list[BaseException] = []
    real_cleanup_directory = videos._cleanup_upload_directory

    def paused_cleanup_directory(child, stale_before, stale_temp_candidates=None):
        if child.name == fixed_id:
            sweep_entered.set()
            assert release_sweep.wait(5), "test did not release orphan sweep"
        return real_cleanup_directory(child, stale_before, stale_temp_candidates)

    monkeypatch.setattr(videos, "_cleanup_upload_directory", paused_cleanup_directory)

    def cleanup_worker():
        try:
            videos.cleanup_expired_uploads()
        except BaseException as exc:
            failures.append(exc)
        finally:
            cleanup_finished.set()

    worker = threading.Thread(target=cleanup_worker, daemon=True)
    worker.start()
    assert sweep_entered.wait(2), "cleanup never reached the orphan candidate"
    try:
        monkeypatch.setattr(videos.uuid, "uuid4", lambda: __import__("uuid").UUID(fixed_id))
        _, token = new_user(client)
        initialized = init_video(client, token, MP4_HEADER + b"new-session-race")
        assert initialized.status_code == 201, initialized.text
        assert initialized.json()["upload_id"] == fixed_id
    finally:
        release_sweep.set()

    worker.join(timeout=5)
    assert cleanup_finished.is_set()
    assert failures == []
    assert directory.is_dir()
    with SessionLocal() as db:
        assert db.get(UploadSession, fixed_id) is not None
