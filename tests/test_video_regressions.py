"""High-value video regressions for crash recovery, auth and route isolation."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from conftest import (
    MP4_HEADER,
    auth,
    init_video,
    new_user,
    put_video_part,
    upload,
    upload_video,
    video_fingerprint,
)


def _sample(size: int = 256) -> bytes:
    assert size >= len(MP4_HEADER)
    return MP4_HEADER + bytes(index % 251 for index in range(size - len(MP4_HEADER)))


@pytest.mark.parametrize("destination_already_moved", [False, True])
def test_finalizing_recovery_is_idempotent_before_and_after_atomic_move(
    client, destination_already_moved
):
    """Startup recovery finishes both durable states without duplicating media."""
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import Image, UploadSession
    from app.services.videos import recover_finalizing_uploads, session_file

    data = _sample()
    _, token = new_user(client)
    initialized = init_video(client, token, data).json()
    upload_id = initialized["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200

    code = f"r{uuid.uuid4().hex[: settings.short_code_length - 1]}"
    relative_path = Path("files") / code[:2] / code[2:4] / f"{code}.mp4"
    destination = settings.data_dir / relative_path
    source = session_file(upload_id)
    recovery_info = {
        "code": code,
        "stored_path": str(relative_path),
        "content_type": "video/mp4",
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        session.status = "finalizing"
        session.resume_info = json.dumps(recovery_info)
        db.commit()

    assert source.is_file()
    assert not destination.exists()
    if destination_already_moved:
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, destination)
        assert destination.is_file()
        assert not source.exists()

    assert recover_finalizing_uploads() == 1
    assert recover_finalizing_uploads() == 0

    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        videos = db.execute(
            select(Image).where(Image.code == code, Image.media_kind == "video")
        ).scalars().all()
        assert session.status == "completed"
        assert session.final_code == code
        assert len(videos) == 1
        assert videos[0].sha256 == recovery_info["sha256"]
        assert db.scalar(
            select(func.count()).select_from(Image).where(Image.code == code)
        ) == 1

    status = client.get(f"/api/video-uploads/{upload_id}", headers=auth(token))
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    assert status.json()["video"]["code"] == code
    response = client.get(f"/v/{code}")
    assert response.status_code == 200
    assert response.content == data


def test_interrupted_verifying_session_returns_to_active(client):
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services.videos import recover_finalizing_uploads

    data = _sample(300)
    _, token = new_user(client)
    initialized = init_video(client, token, data).json()
    upload_id = initialized["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200
    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        session.status = "verifying"
        session.resume_info = json.dumps({"verification_nonce": uuid.uuid4().hex})
        db.commit()

    assert recover_finalizing_uploads() >= 1
    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        assert session.status == "active"
        assert session.resume_info == ""
    assert recover_finalizing_uploads() == 0


def test_finalizing_recovery_rejects_escaped_path_without_touching_sentinel(client):
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services.videos import recover_finalizing_uploads, session_file

    data = _sample(320)
    _, token = new_user(client)
    initialized = init_video(client, token, data).json()
    upload_id = initialized["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200
    source = session_file(upload_id)
    sentinel = settings.data_dir.parent / f"sentinel-{uuid.uuid4().hex}.mp4"
    sentinel.write_bytes(b"do-not-touch")
    code = f"x{uuid.uuid4().hex[: settings.short_code_length - 1]}"
    try:
        with SessionLocal() as db:
            session = db.get(UploadSession, upload_id)
            session.status = "finalizing"
            session.resume_info = json.dumps(
                {
                    "code": code,
                    "stored_path": str(Path("..") / sentinel.name),
                    "content_type": "video/mp4",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            db.commit()

        assert recover_finalizing_uploads() == 1
        assert sentinel.read_bytes() == b"do-not-touch"
        assert source.is_file()
        with SessionLocal() as db:
            session = db.get(UploadSession, upload_id)
            assert session.status == "active"
            assert session.resume_info == ""
    finally:
        sentinel.unlink(missing_ok=True)


def test_destination_prepare_error_restores_verifying_session_for_retry(
    client, monkeypatch
):
    import errno

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services import videos

    data = _sample(336)
    _, token = new_user(client)
    initialized = init_video(client, token, data).json()
    upload_id = initialized["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200
    real_mkdir = Path.mkdir

    def fail_media_destination(path, *args, **kwargs):
        if settings.files_dir == path or settings.files_dir in path.parents:
            raise PermissionError(errno.EACCES, "destination denied", str(path))
        return real_mkdir(path, *args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "mkdir", fail_media_destination)
        failed = client.post(
            f"/api/video-uploads/{upload_id}/complete", headers=auth(token)
        )
    assert failed.status_code == 500, failed.text
    assert failed.json()["detail"] == "could not prepare video storage"
    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        assert session.status == "active"
        assert session.resume_info == ""
    assert videos.session_file(upload_id).is_file()

    retried = client.post(
        f"/api/video-uploads/{upload_id}/complete", headers=auth(token)
    )
    assert retried.status_code == 200, retried.text


def test_cancel_finalizing_session_removes_already_moved_destination(
    client, monkeypatch
):
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services import videos

    data = _sample(352)
    _, token = new_user(client)
    initialized = init_video(client, token, data).json()
    upload_id = initialized["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200

    def fail_after_move(*_args, **_kwargs):
        raise RuntimeError("simulated metadata commit failure")

    monkeypatch.setattr(videos, "_create_final_image", fail_after_move)
    with pytest.raises(RuntimeError, match="metadata commit failure"):
        client.post(
            f"/api/video-uploads/{upload_id}/complete", headers=auth(token)
        )

    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        assert session.status == "finalizing"
        info = json.loads(session.resume_info)
        destination = settings.data_dir / info["stored_path"]
        assert destination.is_file()
        assert not videos.session_file(upload_id).exists()

    canceled = client.delete(
        f"/api/video-uploads/{upload_id}", headers=auth(token)
    )
    assert canceled.status_code == 204, canceled.text
    assert not destination.exists()
    with SessionLocal() as db:
        assert db.get(UploadSession, upload_id) is None


def test_part_disk_shortage_leaves_no_artifacts_and_can_retry(client, monkeypatch):
    from app.core.database import SessionLocal
    from app.models import UploadPart
    from app.services import videos

    data = _sample()
    _, token = new_user(client)
    initialized = init_video(client, token, data).json()
    upload_id = initialized["upload_id"]
    upload_dir = videos.session_dir(upload_id)

    free_space = {"bytes": 10}
    monkeypatch.setattr(videos.settings, "min_free_space_mb", 1)
    monkeypatch.setattr(
        videos.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"free": free_space["bytes"]})(),
    )

    unavailable = put_video_part(client, token, upload_id, 0, data, 0, len(data))
    assert unavailable.status_code == 507
    assert not videos.session_file(upload_id).exists()
    assert list(upload_dir.glob("*.tmp")) == []
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count()).select_from(UploadPart).where(UploadPart.upload_id == upload_id)
        ) == 0

    free_space["bytes"] = 1 << 40
    retried = put_video_part(client, token, upload_id, 0, data, 0, len(data))
    assert retried.status_code == 200
    assert list(upload_dir.glob("*.tmp")) == []
    status = client.get(f"/api/video-uploads/{upload_id}", headers=auth(token)).json()
    assert status["status"] == "active"
    assert status["uploaded_parts"] == [0]


def test_team_access_is_rechecked_at_completion_and_session_remains_retryable(client):
    from app.core.database import SessionLocal
    from app.models import Image, UploadSession

    _, owner = new_user(client)
    member_name, member = new_user(client)
    team_id = client.post(
        "/api/teams", headers=auth(owner), json={"name": f"video-team-{uuid.uuid4().hex[:8]}"}
    ).json()["id"]
    membership = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner),
        json={"username": member_name},
    ).json()

    data = _sample()
    initialized = init_video(client, member, data, team_id=team_id).json()
    upload_id = initialized["upload_id"]
    assert put_video_part(client, member, upload_id, 0, data, 0, len(data)).status_code == 200
    assert client.delete(
        f"/api/teams/{team_id}/members/{membership['id']}", headers=auth(owner)
    ).status_code == 204

    denied = client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(member))
    assert denied.status_code == 403
    with SessionLocal() as db:
        session = db.get(UploadSession, upload_id)
        assert session.status == "active"
        assert session.final_code is None
        assert db.scalar(
            select(func.count())
            .select_from(Image)
            .where(Image.owner_id == session.owner_id, Image.media_kind == "video")
        ) == 0

    rejoined = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner),
        json={"username": member_name},
    )
    assert rejoined.status_code == 201
    completed = client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(member))
    assert completed.status_code == 200
    assert completed.json()["team_id"] == team_id


def _assert_partial_headers(response, start: int, end: int, total: int, visibility: str) -> None:
    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes {start}-{end}/{total}"
    assert response.headers["content-length"] == str(end - start + 1)
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-content-type-options"] == "nosniff"
    cache_control = response.headers["cache-control"]
    if visibility == "private":
        assert "no-store" in cache_control
    else:
        assert cache_control == "public, max-age=0, must-revalidate"


def _assert_invalid_range_headers(response, total: int, visibility: str) -> None:
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{total}"
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-content-type-options"] == "nosniff"
    cache_control = response.headers["cache-control"]
    if visibility == "private":
        assert "no-store" in cache_control
    else:
        assert cache_control == "public, max-age=0, must-revalidate"


def test_video_range_boundaries_and_error_responses_keep_security_headers(client):
    data = _sample(257)
    _, token = new_user(client)
    _, video = upload_video(client, token, data, visibility="public")
    url = f"/v/{video['code']}"
    last = len(data) - 1

    first_byte = client.get(url, headers={"Range": "bytes=0-0"})
    _assert_partial_headers(first_byte, 0, 0, len(data), "public")
    assert first_byte.content == data[:1]

    open_ended = client.get(url, headers={"Range": "bytes=17-"})
    _assert_partial_headers(open_ended, 17, last, len(data), "public")
    assert open_ended.content == data[17:]

    clamped = client.get(url, headers={"Range": "bytes=23-999999"})
    _assert_partial_headers(clamped, 23, last, len(data), "public")
    assert clamped.content == data[23:]

    large_suffix = client.get(url, headers={"Range": "bytes=-999999"})
    _assert_partial_headers(large_suffix, 0, last, len(data), "public")
    assert large_suffix.content == data

    for invalid_range in ("bytes=-0", "bytes=19-7"):
        invalid = client.get(url, headers={"Range": invalid_range})
        _assert_invalid_range_headers(invalid, len(data), "public")

    _, private_video = upload_video(client, token, _sample(258), visibility="private")
    private_url = f"/v/{private_video['code']}"
    private_partial = client.get(
        private_url, headers={**auth(token), "Range": "bytes=0-0"}
    )
    _assert_partial_headers(private_partial, 0, 0, 258, "private")
    private_invalid = client.get(
        private_url, headers={**auth(token), "Range": "bytes=-0"}
    )
    _assert_invalid_range_headers(private_invalid, 258, "private")


def test_x_api_key_can_complete_and_list_a_video(client):
    _, token = new_user(client)
    key = client.post("/api/keys", headers=auth(token), json={"name": "video-client"}).json()[
        "key"
    ]
    key_headers = {"X-API-Key": key}
    data = _sample()
    payload = {
        "filename": "api-key.mp4",
        "size": len(data),
        "name": "API key video",
        "visibility": "public",
        "team_id": None,
        "fingerprint": video_fingerprint(data),
    }
    initialized = client.post("/api/video-uploads", headers=key_headers, json=payload)
    assert initialized.status_code == 201
    upload_id = initialized.json()["upload_id"]
    part_headers = {
        **key_headers,
        "Content-Type": "application/octet-stream",
        "Content-Range": f"bytes 0-{len(data) - 1}/{len(data)}",
        "X-Chunk-SHA256": hashlib.sha256(data).hexdigest(),
    }
    part = client.put(
        f"/api/video-uploads/{upload_id}/parts/0", headers=part_headers, content=data
    )
    assert part.status_code == 200
    completed = client.post(f"/api/video-uploads/{upload_id}/complete", headers=key_headers)
    assert completed.status_code == 200
    code = completed.json()["code"]
    listed = client.get("/api/videos?limit=100", headers=key_headers)
    assert listed.status_code == 200
    assert code in {item["code"] for item in listed.json()["items"]}


def test_image_and_video_management_routes_are_bidirectionally_isolated(client):
    _, token = new_user(client)
    image_code = upload(client, token, visibility="private").json()["code"]
    _, video = upload_video(client, token, visibility="private")
    video_code = video["code"]

    assert client.patch(
        f"/api/images/{video_code}", headers=auth(token), json={"name": "wrong route"}
    ).status_code == 404
    assert client.get(f"/api/images/{video_code}/link", headers=auth(token)).status_code == 404
    assert client.delete(f"/api/images/{video_code}", headers=auth(token)).status_code == 404
    assert client.get(f"/v/{video_code}", headers=auth(token)).status_code == 200

    assert client.patch(
        f"/api/videos/{image_code}", headers=auth(token), json={"name": "wrong route"}
    ).status_code == 404
    assert client.get(f"/api/videos/{image_code}/link", headers=auth(token)).status_code == 404
    assert client.delete(f"/api/videos/{image_code}", headers=auth(token)).status_code == 404
    assert client.get(f"/i/{image_code}", headers=auth(token)).status_code == 200
