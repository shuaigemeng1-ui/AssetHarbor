"""Resumable video protocol, permissions, integrity and byte-range delivery."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from conftest import (
    MP4_HEADER,
    auth,
    init_video,
    new_user,
    put_video_part,
    upload,
    upload_video,
    url_path,
    video_fingerprint,
)


def _sample(size=64):
    assert size >= len(MP4_HEADER)
    return MP4_HEADER + bytes((i % 251 for i in range(size - len(MP4_HEADER))))


def test_video_upload_requires_auth_and_valid_payload(client):
    data = _sample()
    payload = {
        "filename": "clip.mp4",
        "size": len(data),
        "name": "clip",
        "visibility": "public",
        "fingerprint": video_fingerprint(data),
    }
    assert client.post("/api/video-uploads", json=payload).status_code == 401

    _, token = new_user(client)
    payload["fingerprint"] = "not-a-digest"
    assert client.post("/api/video-uploads", headers=auth(token), json=payload).status_code == 422
    payload["fingerprint"] = "0" * 64
    payload["visibility"] = "secret"
    assert client.post("/api/video-uploads", headers=auth(token), json=payload).status_code == 422


def test_initialize_status_resume_and_owner_isolation(client):
    data = _sample()
    _, owner = new_user(client)
    _, other = new_user(client)
    created = init_video(client, owner, data, name="演示视频", visibility="private")
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "active"
    assert body["chunk_size"] == 1024 * 1024
    assert body["total_parts"] == 1
    assert body["uploaded_parts"] == []
    assert body["expires_at"]

    # Re-initializing the same file and immutable metadata returns the durable session.
    resumed = init_video(client, owner, data, name="  演示视频  ", visibility="private")
    assert resumed.status_code == 201
    assert resumed.json()["upload_id"] == body["upload_id"]
    assert client.get(f"/api/video-uploads/{body['upload_id']}", headers=auth(owner)).status_code == 200
    assert client.get(f"/api/video-uploads/{body['upload_id']}", headers=auth(other)).status_code == 404


def test_session_reuse_includes_visibility_name_and_original_filename(client):
    data = _sample()
    _, token = new_user(client)
    base = init_video(
        client,
        token,
        data,
        filename="folder/original.mp4",
        name="Launch",
        visibility="public",
    )
    assert base.status_code == 201
    base_id = base.json()["upload_id"]

    # Normalized filename/name and identical visibility remain idempotent.
    same = init_video(
        client,
        token,
        data,
        filename="C:\\incoming\\original.mp4",
        name="  Launch  ",
        visibility="public",
    )
    assert same.status_code == 201
    assert same.json()["upload_id"] == base_id

    private = init_video(
        client, token, data, filename="original.mp4", name="Launch", visibility="private"
    )
    renamed = init_video(
        client, token, data, filename="original.mp4", name="Launch private", visibility="public"
    )
    refiled = init_video(
        client, token, data, filename="another.mp4", name="Launch", visibility="public"
    )
    assert private.status_code == renamed.status_code == refiled.status_code == 201
    ids = {
        base_id,
        private.json()["upload_id"],
        renamed.json()["upload_id"],
        refiled.json()["upload_id"],
    }
    assert len(ids) == 4


def test_configured_size_boundary_without_allocating_gigabytes(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_video_size_mb", 1)
    _, token = new_user(client)
    at_limit = b"x" * (1024 * 1024)
    assert init_video(client, token, at_limit).status_code == 201
    too_large = at_limit + b"x"
    assert init_video(client, token, too_large).status_code == 413


def test_free_space_reserve_returns_507(client, monkeypatch):
    from app.services import videos

    _, token = new_user(client)
    monkeypatch.setattr(videos.settings, "min_free_space_mb", 1)
    monkeypatch.setattr(videos.shutil, "disk_usage", lambda _path: type("Usage", (), {"free": 10})())
    assert init_video(client, token, _sample()).status_code == 507


def test_maximum_active_sessions_per_user(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "max_active_video_uploads", 1)
    _, token = new_user(client)
    assert init_video(client, token, _sample(64)).status_code == 201
    assert init_video(client, token, _sample(65)).status_code == 429


def test_part_headers_length_hash_and_range_are_enforced(client):
    data = _sample()
    _, token = new_user(client)
    upload_id = init_video(client, token, data).json()["upload_id"]
    endpoint = f"/api/video-uploads/{upload_id}/parts/0"

    assert client.put(endpoint, headers=auth(token), content=data).status_code == 400
    bad_range = {
        **auth(token),
        "Content-Range": f"bytes 1-{len(data)}/{len(data)}",
        "X-Chunk-SHA256": hashlib.sha256(data).hexdigest(),
    }
    assert client.put(endpoint, headers=bad_range, content=data).status_code == 416
    bad_hash = {
        **auth(token),
        "Content-Range": f"bytes 0-{len(data)-1}/{len(data)}",
        "X-Chunk-SHA256": "0" * 64,
    }
    assert client.put(endpoint, headers=bad_hash, content=data).status_code == 409

    short = data[:-1]
    short_headers = {
        **auth(token),
        "Content-Range": f"bytes 0-{len(data)-1}/{len(data)}",
        "X-Chunk-SHA256": hashlib.sha256(short).hexdigest(),
    }
    assert client.put(endpoint, headers=short_headers, content=short).status_code == 400


def test_unsupported_magic_rejected_even_with_mp4_name_and_mime(client):
    data = b"definitely not an mp4 container"
    _, token = new_user(client)
    upload_id = init_video(client, token, data, filename="forged.mp4").json()["upload_id"]
    response = put_video_part(client, token, upload_id, 0, data, 0, len(data))
    assert response.status_code == 415


def test_part_idempotence_conflict_and_authoritative_status(client):
    data = _sample()
    _, token = new_user(client)
    info = init_video(client, token, data).json()
    upload_id = info["upload_id"]

    first = put_video_part(client, token, upload_id, 0, data, 0, len(data))
    assert first.status_code == 200
    assert first.json() == {
        "part_number": 0,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200

    different = bytearray(data)
    different[-1] ^= 1
    assert put_video_part(client, token, upload_id, 0, bytes(different), 0, len(data)).status_code == 409
    status = client.get(f"/api/video-uploads/{upload_id}", headers=auth(token)).json()
    assert status["uploaded_parts"] == [0]


def test_out_of_order_parts_missing_complete_and_atomic_finalize(client):
    from app.core.config import settings

    data = _sample(1024 * 1024 + 137)
    _, token = new_user(client)
    initialized = init_video(client, token, data, name="large sample").json()
    upload_id = initialized["upload_id"]
    split = initialized["chunk_size"]

    assert put_video_part(client, token, upload_id, 1, data[split:], split, len(data)).status_code == 200
    assert client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(token)).status_code == 409
    assert put_video_part(client, token, upload_id, 0, data[:split], 0, len(data)).status_code == 200

    completed = client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(token))
    assert completed.status_code == 200
    video = completed.json()
    assert video["media_kind"] == "video"
    assert video["sha256"] == hashlib.sha256(data).hexdigest()
    assert video["url"].endswith(f"/v/{video['code']}")
    assert not (settings.uploads_dir / upload_id / "video.part").exists()

    # Completion is idempotent and status exposes the final object.
    again = client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(token))
    assert again.status_code == 200 and again.json()["code"] == video["code"]
    status = client.get(f"/api/video-uploads/{upload_id}", headers=auth(token)).json()
    assert status["status"] == "completed" and status["video"]["code"] == video["code"]


def test_fingerprint_is_rechecked_at_completion(client):
    data = _sample()
    _, token = new_user(client)
    response = init_video(client, token, data, fingerprint="0" * 64)
    upload_id = response.json()["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200
    assert client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(token)).status_code == 409


def test_cancel_removes_pending_data_but_completed_video_survives(client):
    from app.core.config import settings

    data = _sample()
    _, token = new_user(client)
    pending = init_video(client, token, data).json()
    assert put_video_part(client, token, pending["upload_id"], 0, data, 0, len(data)).status_code == 200
    temp_dir = settings.uploads_dir / pending["upload_id"]
    assert temp_dir.exists()
    assert client.delete(f"/api/video-uploads/{pending['upload_id']}", headers=auth(token)).status_code == 204
    assert not temp_dir.exists()
    assert client.get(f"/api/video-uploads/{pending['upload_id']}", headers=auth(token)).status_code == 404

    session, video = upload_video(client, token, data)
    assert client.delete(f"/api/video-uploads/{session['upload_id']}", headers=auth(token)).status_code == 204
    assert client.get(f"/v/{video['code']}").status_code == 200


def test_expired_session_returns_410_and_is_cleaned(client):
    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models import UploadSession
    from app.services.videos import _now

    data = _sample()
    _, token = new_user(client)
    created = init_video(client, token, data).json()
    upload_id = created["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200
    with SessionLocal() as db:
        row = db.get(UploadSession, upload_id)
        row.expires_at = _now() - timedelta(seconds=1)
        db.commit()
    assert client.get(f"/api/video-uploads/{upload_id}", headers=auth(token)).status_code == 410
    assert not (settings.uploads_dir / upload_id).exists()


def test_public_video_range_suffix_unsatisfiable_and_download(client):
    data = _sample(128)
    _, token = new_user(client)
    _, video = upload_video(client, token, data, filename="演示 clip.mp4", visibility="public")
    url = f"/v/{video['code']}"

    full = client.get(url)
    assert full.status_code == 200 and full.content == data
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["x-content-type-options"] == "nosniff"
    assert "immutable" in full.headers["cache-control"]

    partial = client.get(url, headers={"Range": "bytes=5-12"})
    assert partial.status_code == 206 and partial.content == data[5:13]
    assert partial.headers["content-range"] == f"bytes 5-12/{len(data)}"
    suffix = client.get(url, headers={"Range": "bytes=-7"})
    assert suffix.status_code == 206 and suffix.content == data[-7:]

    invalid = client.get(url, headers={"Range": f"bytes={len(data)}-"})
    assert invalid.status_code == 416
    assert invalid.headers["content-range"] == f"bytes */{len(data)}"
    multiple = client.get(url, headers={"Range": "bytes=0-1,3-4"})
    assert multiple.status_code == 416

    download = client.get(url + "?download=1")
    assert "attachment" in download.headers["content-disposition"]
    assert "filename*=UTF-8''" in download.headers["content-disposition"]


def test_private_video_owner_signed_link_and_revocation(client):
    data = _sample()
    _, owner = new_user(client)
    _, other = new_user(client)
    _, video = upload_video(client, owner, data, visibility="private")
    code = video["code"]

    assert client.get(f"/v/{code}").status_code == 404
    assert client.get(f"/v/{code}", headers=auth(other)).status_code == 404
    own = client.get(f"/v/{code}", headers={**auth(owner), "Range": "bytes=0-3"})
    assert own.status_code == 206 and own.content == data[:4]
    assert "no-store" in own.headers["cache-control"]

    link = client.get(f"/api/videos/{code}/link", headers=auth(owner))
    assert link.status_code == 200
    path = "/" + url_path(link.json()["url"])
    assert client.get(path, headers={"Range": "bytes=1-2"}).status_code == 206
    assert client.get(path.replace("sig=", "sig=bad")).status_code == 404
    assert client.get(f"/api/videos/{code}/link", headers=auth(other)).status_code == 404

    # public -> private increments the signing version and revokes an old URL.
    assert client.patch(f"/api/videos/{code}", headers=auth(owner), json={"visibility": "public"}).status_code == 200
    old_path = "/" + url_path(client.get(f"/api/videos/{code}/link", headers=auth(owner)).json()["url"])
    assert client.patch(f"/api/videos/{code}", headers=auth(owner), json={"visibility": "private"}).status_code == 200
    assert client.get(old_path).status_code == 404


def test_video_and_image_routes_and_lists_stay_separate(client):
    _, token = new_user(client)
    image_code = upload(client, token).json()["code"]
    _, video = upload_video(client, token)
    video_code = video["code"]

    videos = client.get("/api/videos", headers=auth(token)).json()
    images = client.get("/api/images?limit=100", headers=auth(token)).json()
    assert video_code in {item["code"] for item in videos["items"]}
    assert image_code not in {item["code"] for item in videos["items"]}
    assert image_code in {item["code"] for item in images["items"]}
    assert video_code not in {item["code"] for item in images["items"]}
    assert client.get(f"/i/{video_code}").status_code == 404
    assert client.get(f"/v/{image_code}").status_code == 404


def test_team_video_permissions_space_and_disband_transfer(client):
    _, owner = new_user(client)
    member_name, member = new_user(client)
    _, outsider = new_user(client)
    team_id = client.post("/api/teams", headers=auth(owner), json={"name": "video-team"}).json()["id"]
    client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner),
        json={"username": member_name},
    )
    data = _sample()
    pending = init_video(client, member, data, team_id=team_id, visibility="private")
    assert pending.status_code == 201
    upload_id = pending.json()["upload_id"]
    assert init_video(client, outsider, _sample(65), team_id=team_id).status_code == 403

    assert put_video_part(client, member, upload_id, 0, data, 0, len(data)).status_code == 200
    video = client.post(f"/api/video-uploads/{upload_id}/complete", headers=auth(member)).json()
    code = video["code"]
    assert client.get(f"/v/{code}", headers=auth(owner)).status_code == 200
    assert client.get(f"/v/{code}", headers=auth(outsider)).status_code == 404
    team_videos = client.get(f"/api/teams/{team_id}/videos", headers=auth(owner)).json()
    assert code in {item["code"] for item in team_videos["items"]}
    assert client.get(f"/api/teams/{team_id}/videos", headers=auth(outsider)).status_code == 404

    # Also keep a pending session and ensure disbanding returns both to uploader.
    pending2 = init_video(client, member, _sample(66), team_id=team_id).json()
    assert client.delete(f"/api/teams/{team_id}", headers=auth(owner)).status_code == 204
    assert client.get("/api/videos", headers=auth(member)).json()["total"] >= 1
    resumed = client.get(
        f"/api/video-uploads/{pending2['upload_id']}", headers=auth(member)
    )
    assert resumed.status_code == 200
    assert resumed.json()["team_id"] is None


def test_deleted_user_pending_upload_is_cleaned(client):
    from app.core.config import settings

    from conftest import login

    admin = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    me = client.get("/api/auth/me", headers=auth(token)).json()
    data = _sample()
    created = init_video(client, token, data).json()
    put_video_part(client, token, created["upload_id"], 0, data, 0, len(data))
    assert client.delete(f"/api/admin/users/{me['id']}", headers=auth(admin)).status_code == 204
    assert not (settings.uploads_dir / created["upload_id"]).exists()


def test_admin_stats_distinguish_images_videos_and_pending_bytes(client):
    from conftest import login

    admin = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    upload(client, token)
    _, _video = upload_video(client, token)
    pending_data = _sample(77)
    init_video(client, token, pending_data)
    body = client.get("/api/admin/stats", headers=auth(admin)).json()
    assert body["images"] >= 1
    assert body["videos"] >= 1
    assert body["media_total"] == body["images"] + body["videos"]
    assert body["pending_upload_bytes"] >= len(pending_data)
