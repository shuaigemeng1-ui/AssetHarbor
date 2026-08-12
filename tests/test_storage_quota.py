"""Per-user/team storage quota admission and release behavior."""

import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import UploadSession, User
from app.services.storage_quota import (
    team_storage_usage_bytes,
    user_storage_usage_bytes,
)
from conftest import MP4_HEADER, auth, init_video, new_user, upload_video


def _video_bytes(size: int, marker: int = 0) -> bytes:
    assert size >= len(MP4_HEADER) + 1
    return MP4_HEADER + bytes([marker % 251]) + b"v" * (size - len(MP4_HEADER) - 1)


def _image_bytes(size: int, marker: int = 0) -> bytes:
    magic = b"\x89PNG\r\n\x1a\n"
    assert size >= len(magic) + 1
    return magic + bytes([marker % 251]) + b"i" * (size - len(magic) - 1)


def _post_image(client, token: str, data: bytes, filename: str):
    return client.post(
        "/api/upload",
        headers=auth(token),
        files={"file": (filename, data, "image/png")},
    )


def _team_with_member(client):
    owner_name, owner = new_user(client)
    member_name, member = new_user(client)
    team = client.post(
        "/api/teams",
        headers=auth(owner),
        json={"name": f"quota-{uuid.uuid4().hex}"},
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    added = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner),
        json={"username": member_name},
    )
    assert added.status_code == 201, added.text
    return owner_name, owner, member_name, member, team_id


def test_image_quota_failure_writes_no_file(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    _, token = new_user(client)
    reservation = _video_bytes(1024 * 1024)
    initialized = init_video(client, token, reservation)
    assert initialized.status_code == 201
    resumed = init_video(client, token, reservation)
    assert resumed.status_code == 201
    assert resumed.json()["upload_id"] == initialized.json()["upload_id"]
    before = {path for path in settings.files_dir.rglob("*") if path.is_file()}

    response = _post_image(client, token, _image_bytes(128), "over-quota.png")

    assert response.status_code == 413
    assert response.json()["detail"] == "user storage quota exceeded"
    after = {path for path in settings.files_dir.rglob("*") if path.is_file()}
    assert after == before


def test_concurrent_video_initialization_cannot_oversell_user_quota(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    _, token = new_user(client)
    start = threading.Barrier(3)
    results = []

    def initialize(marker: int):
        data = _video_bytes(600 * 1024, marker)
        start.wait()
        results.append(init_video(client, token, data, filename=f"race-{marker}.mp4"))

    threads = [threading.Thread(target=initialize, args=(marker,)) for marker in (1, 2)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=5)

    assert sorted(response.status_code for response in results) == [201, 413]
    rejected = next(response for response in results if response.status_code == 413)
    assert rejected.json()["detail"] == "user storage quota exceeded"


def test_team_uploads_enforce_user_and_team_quotas(client, monkeypatch):
    chunk = 600 * 1024

    # Team space is available, but the uploader's personal+team aggregate is not.
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    monkeypatch.setattr(settings, "team_storage_quota_mb", 10)
    _, owner, _, _member, team_id = _team_with_member(client)
    assert init_video(client, owner, _video_bytes(chunk, 1)).status_code == 201
    user_limited = init_video(
        client, owner, _video_bytes(chunk, 2), team_id=team_id
    )
    assert user_limited.status_code == 413
    assert user_limited.json()["detail"] == "user storage quota exceeded"

    # Different users share one team ceiling; each still has ample user quota.
    monkeypatch.setattr(settings, "user_storage_quota_mb", 10)
    monkeypatch.setattr(settings, "team_storage_quota_mb", 1)
    _, owner2, _, member2, team2 = _team_with_member(client)
    assert init_video(
        client, owner2, _video_bytes(chunk, 3), team_id=team2
    ).status_code == 201
    team_limited = init_video(
        client, member2, _video_bytes(chunk, 4), team_id=team2
    )
    assert team_limited.status_code == 413
    assert team_limited.json()["detail"] == "team storage quota exceeded"


def test_cancel_and_media_delete_release_quota(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)

    # Cancel releases the declared reservation of an unfinished video.
    _, video_token = new_user(client)
    first = init_video(client, video_token, _video_bytes(700 * 1024, 1))
    assert first.status_code == 201
    second_data = _video_bytes(700 * 1024, 2)
    assert init_video(client, video_token, second_data).status_code == 413
    assert client.delete(
        f"/api/video-uploads/{first.json()['upload_id']}",
        headers=auth(video_token),
    ).status_code == 204
    assert init_video(client, video_token, second_data).status_code == 201

    # Deleting completed media releases the same user's completed-byte usage.
    _, image_token = new_user(client)
    image_data = _image_bytes(600 * 1024)
    first_image = _post_image(client, image_token, image_data, "first.png")
    assert first_image.status_code == 201
    assert _post_image(client, image_token, image_data, "second.png").status_code == 413
    assert client.delete(
        f"/api/images/{first_image.json()['code']}", headers=auth(image_token)
    ).status_code == 204
    assert _post_image(client, image_token, image_data, "second.png").status_code == 201


def test_user_quotas_are_isolated_and_zero_is_unlimited(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    _, first_user = new_user(client)
    _, second_user = new_user(client)
    assert init_video(
        client, first_user, _video_bytes(900 * 1024, 1)
    ).status_code == 201
    assert init_video(
        client, second_user, _video_bytes(900 * 1024, 2)
    ).status_code == 201

    monkeypatch.setattr(settings, "user_storage_quota_mb", 0)
    monkeypatch.setattr(settings, "team_storage_quota_mb", 0)
    _, unlimited = new_user(client)
    assert init_video(
        client, unlimited, _video_bytes(1536 * 1024, 3)
    ).status_code == 201
    assert init_video(
        client, unlimited, _video_bytes(1536 * 1024, 4)
    ).status_code == 201


def test_usage_helpers_count_owner_across_spaces_and_team_reservations(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 0)
    monkeypatch.setattr(settings, "team_storage_quota_mb", 0)
    owner_name, owner, _, _member, team_id = _team_with_member(client)
    personal_size = 256 * 1024
    team_size = 384 * 1024
    personal = init_video(client, owner, _video_bytes(personal_size, 1))
    team = init_video(client, owner, _video_bytes(team_size, 2), team_id=team_id)
    assert personal.status_code == team.status_code == 201

    with SessionLocal() as db:
        owner_id = db.execute(
            select(User.id).where(User.username == owner_name)
        ).scalar_one()
        assert user_storage_usage_bytes(db, owner_id) == personal_size + team_size
        assert team_storage_usage_bytes(db, team_id) == team_size
        assert db.get(UploadSession, personal.json()["upload_id"]).status == "active"


def test_video_completion_replaces_reservation_without_double_counting(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    _, token = new_user(client)
    completed_size = 600 * 1024
    _, completed = upload_video(client, token, _video_bytes(completed_size, 1))

    with SessionLocal() as db:
        owner = db.get(User, completed["owner_id"])
        assert owner is not None
        assert user_storage_usage_bytes(db, owner.id) == completed_size

    # Exactly fill the remaining 424 KiB. A completed session must not count
    # alongside the final Image row or this admission would be rejected.
    remaining = 424 * 1024
    assert init_video(
        client, token, _video_bytes(remaining, 2), filename="remaining.mp4"
    ).status_code == 201


def test_expired_session_no_longer_consumes_logical_quota_before_cleanup(client, monkeypatch):
    monkeypatch.setattr(settings, "user_storage_quota_mb", 1)
    _, token = new_user(client)
    first = init_video(client, token, _video_bytes(1024 * 1024, 1))
    assert first.status_code == 201

    with SessionLocal() as db:
        upload = db.get(UploadSession, first.json()["upload_id"])
        upload.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()

    # Physical stale bytes remain protected by the global free-space reserve,
    # but an already expired logical reservation must not lock the account
    # until the next hourly cleanup sweep.
    second = init_video(
        client,
        token,
        _video_bytes(1024 * 1024, 2),
        filename="after-expiry.mp4",
    )
    assert second.status_code == 201, second.text
