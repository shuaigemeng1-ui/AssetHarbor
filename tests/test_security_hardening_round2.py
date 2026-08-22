"""Second-round adversarial security regressions."""

from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from pydantic import ValidationError
from sqlalchemy import select

from conftest import (
    FAKE_PNG,
    MP4_HEADER,
    auth,
    init_video,
    login,
    new_user,
    put_video_part,
    upload,
    upload_video,
)
from app.core import security
from app.core.config import Settings, settings
from app.core.database import SessionLocal
from app.main import app
from app.models import ApiKey, Image, UploadSession
from app.models.base import utcnow
from app.services.videos import cleanup_expired_uploads


def _new_key(client, token: str, name: str = "automation") -> tuple[int, str]:
    response = client.post("/api/keys", headers=auth(token), json={"name": name})
    assert response.status_code == 201, response.text
    return response.json()["id"], response.json()["key"]


def test_api_keys_cannot_reach_control_plane_or_credential_routes(client):
    _, user_token = new_user(client)
    _, user_key = _new_key(client, user_token)
    admin_token = login(client, "admin", "admin-pass")
    _, admin_key = _new_key(client, admin_token, "admin-automation")

    assert client.get("/api/auth/me", headers={"X-API-Key": user_key}).status_code == 200
    # Data-plane upload remains available with either documented API-key form.
    assert upload(client, user_key, data={"visibility": "public"}).status_code == 201
    assert client.post(
        "/api/upload",
        headers={"X-API-Key": user_key},
        files={"file": ("key.png", FAKE_PNG, "image/png")},
    ).status_code == 201

    jwt_only_requests = (
        ("post", "/api/auth/change-password", {"json": {"old_password": "pass123", "new_password": "newpass1"}}),
        ("get", "/api/keys", {}),
        ("post", "/api/teams", {"json": {"name": "api-key-must-not-create-team"}}),
        ("get", "/api/teams", {}),
        ("post", "/api/media-groups", {"json": {"name": "forbidden", "codes": []}}),
    )
    for method, path, kwargs in jwt_only_requests:
        response = getattr(client, method)(path, headers={"X-API-Key": user_key}, **kwargs)
        assert response.status_code == 403, (method, path, response.text)

    # Even an API key owned by a global administrator is not a control-plane credential.
    assert client.get("/api/admin/stats", headers={"X-API-Key": admin_key}).status_code == 403
    assert client.get("/api/users", headers={"X-API-Key": admin_key}).status_code == 403


def test_multiple_or_oversized_credentials_fail_closed(client):
    _, first_token = new_user(client)
    _, second_token = new_user(client)
    _, first_key = _new_key(client, first_token)

    ambiguous = client.get(
        "/api/auth/me",
        headers={**auth(second_token), "X-API-Key": first_key},
    )
    assert ambiguous.status_code == 400
    assert "multiple authentication" in ambiguous.json()["detail"]

    oversized = "x" * (security._MAX_CREDENTIAL_LENGTH + 1)
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {oversized}"}).status_code == 401
    assert client.get("/api/auth/me", headers={"X-API-Key": oversized}).status_code == 401
    assert client.post(
        "/api/auth/login",
        data={"username": "u" * 65, "password": "p" * 129},
    ).status_code == 401


def test_api_key_usage_touch_failure_never_breaks_authentication(client, monkeypatch):
    _, token = new_user(client)
    _, key = _new_key(client, token)

    class BrokenUsageSession:
        def __enter__(self):
            raise RuntimeError("simulated busy telemetry database")

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(security, "SessionLocal", BrokenUsageSession)
    response = client.get("/api/auth/me", headers={"X-API-Key": key})
    assert response.status_code == 200


def test_api_key_count_is_bounded_but_rotation_does_not_consume_slot(client, monkeypatch):
    _, token = new_user(client)
    monkeypatch.setattr(settings, "max_api_keys_per_user", 2)
    first_id, _ = _new_key(client, token, "first")
    _new_key(client, token, "second")
    rejected = client.post("/api/keys", headers=auth(token), json={"name": "third"})
    assert rejected.status_code == 409
    assert client.post(f"/api/keys/{first_id}/rotate", headers=auth(token)).status_code == 200


def _dependency_calls(route: APIRoute) -> set[object]:
    calls: set[object] = set()

    def visit(dependant) -> None:
        if dependant.call is not None:
            calls.add(dependant.call)
        for child in dependant.dependencies:
            visit(child)

    visit(route.dependant)
    return calls


def test_every_nonpublic_api_route_has_authentication_dependency():
    explicitly_public = {
        ("GET", "/api/auth/config"),
        ("POST", "/api/auth/login"),
        ("POST", "/api/auth/register"),
        ("GET", "/api/media/{code}"),
        ("GET", "/api/media/{code}/link"),
    }
    authentication_dependencies = {
        security.get_current_user,
        security.get_optional_user,
        security.require_jwt_user,
        security.require_jwt_admin,
    }
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/"):
            continue
        calls = _dependency_calls(route)
        for method in route.methods:
            if (method, route.path) in explicitly_public:
                assert security.get_optional_user in calls or route.path.startswith("/api/auth/")
            else:
                assert calls & authentication_dependencies, f"{method} {route.path} has no auth dependency"
            if route.path.startswith("/api/admin/") or route.path == "/api/users":
                assert security.require_jwt_admin in calls


@pytest.mark.parametrize("media_kind", ["image", "video"])
def test_corrupt_media_path_cannot_read_or_delete_outside_files(client, media_kind):
    _, token = new_user(client)
    owner_id = client.get("/api/auth/me", headers=auth(token)).json()["id"]
    sentinel = settings.data_dir.parent / f"oss-path-sentinel-{media_kind}.bin"
    sentinel.write_bytes(b"must-survive")
    try:
        code = f"escape{1 if media_kind == 'image' else 2}"
        with SessionLocal() as db:
            db.add(
                Image(
                    code=code,
                    original_filename=f"outside.{media_kind}",
                    name="outside",
                    stored_path=str(Path("..") / sentinel.name),
                    content_type="image/png" if media_kind == "image" else "video/mp4",
                    size=sentinel.stat().st_size,
                    sha256="0" * 64,
                    media_kind=media_kind,
                    owner_id=owner_id,
                    visibility="public",
                )
            )
            db.commit()

        direct_prefix = "i" if media_kind == "image" else "v"
        api_prefix = "images" if media_kind == "image" else "videos"
        assert client.get(f"/{direct_prefix}/{code}").status_code == 404
        assert client.delete(f"/api/{api_prefix}/{code}", headers=auth(token)).status_code == 204
        assert sentinel.read_bytes() == b"must-survive"
    finally:
        sentinel.unlink(missing_ok=True)


def test_corrupt_upload_id_cleanup_never_removes_outside_directory(client):
    _, token = new_user(client)
    user_id = client.get("/api/auth/me", headers=auth(token)).json()["id"]
    outside = settings.data_dir / "outside-upload-sentinel"
    outside.mkdir(exist_ok=True)
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    corrupt_id = "../outside-upload-sentinel"
    with SessionLocal() as db:
        db.add(
            UploadSession(
                upload_id=corrupt_id,
                owner_id=user_id,
                original_filename="corrupt.mp4",
                name="corrupt",
                visibility="public",
                size=1,
                chunk_size=1,
                total_parts=1,
                fingerprint="0" * 64,
                status="active",
                expires_at=utcnow() - timedelta(days=1),
                resume_info="",
                created_at=utcnow() - timedelta(days=2),
                updated_at=utcnow() - timedelta(days=2),
            )
        )
        db.commit()

    cleanup_expired_uploads()
    assert sentinel.read_text(encoding="utf-8") == "keep"
    with SessionLocal() as db:
        assert db.get(UploadSession, corrupt_id) is None


def test_security_headers_and_api_no_store_preserve_media_cache(client):
    login_response = client.post(
        "/api/auth/login", data={"username": "admin", "password": "admin-pass"}
    )
    assert login_response.status_code == 200
    assert login_response.headers["cache-control"] == "no-store"
    assert login_response.headers["x-content-type-options"] == "nosniff"
    assert login_response.headers["referrer-policy"] == "no-referrer"
    assert login_response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "default-src 'none'" in login_response.headers["content-security-policy"]

    created_key = client.post("/api/keys", headers=auth(login_response.json()["access_token"]))
    assert created_key.headers["cache-control"] == "no-store"

    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "public"}).json()["code"]
    image = client.get(f"/i/{code}")
    assert image.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert image.headers["x-content-type-options"] == "nosniff"

    docs = client.get("/docs")
    assert "frame-ancestors 'none'" in docs.headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline'" in docs.headers["content-security-policy"]
    openapi = client.get("/openapi.json")
    assert openapi.headers["cache-control"] == "no-store"
    assert "default-src 'none'" in openapi.headers["content-security-policy"]
    schema = openapi.json()
    assert schema["components"]["securitySchemes"]["ApiKeyAuth"] == {
        "type": "apiKey",
        "description": "Long-lived media data-plane credential; control-plane operations require JWT.",
        "in": "header",
        "name": "X-API-Key",
    }
    data_security = schema["paths"]["/api/images"]["get"]["security"]
    assert {"OAuth2PasswordBearer": []} in data_security
    assert {"ApiKeyAuth": []} in data_security
    for path, method in (("/api/keys", "post"), ("/api/admin/stats", "get")):
        control_security = schema["paths"][path][method]["security"]
        assert {"OAuth2PasswordBearer": []} in control_security
        assert {"ApiKeyAuth": []} not in control_security
    for path in (
        "/i/{code}",
        "/v/{code}",
        "/api/media/{code}",
        "/api/media/{code}/link",
    ):
        optional_security = schema["paths"][path]["get"]["security"]
        assert {} in optional_security
        assert {"OAuth2PasswordBearer": []} in optional_security
        assert {"ApiKeyAuth": []} in optional_security


def test_short_configured_jwt_secret_is_rejected():
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(
            _env_file=None,
            _env_prefix="OSS_SECURITY_TEST_",
            jwt_secret="guessable-secret",
        )

    assert Settings(
        _env_file=None,
        _env_prefix="OSS_SECURITY_TEST_",
        jwt_secret="",
    ).jwt_secret == ""


def test_image_metadata_strips_client_paths_and_bounds_names(client):
    _, token = new_user(client)
    created = client.post(
        "/api/upload",
        headers=auth(token),
        files={"file": ("../../private-folder/photo.png", FAKE_PNG, "image/png")},
    )
    assert created.status_code == 201
    item = client.get("/api/images", headers=auth(token)).json()["items"][0]
    assert item["original_filename"] == "photo.png"
    assert "/" not in item["original_filename"]

    rejected = client.post(
        "/api/upload",
        headers=auth(token),
        data={"name": "x" * 256},
        files={"file": ("photo.png", FAKE_PNG, "image/png")},
    )
    assert rejected.status_code == 422


def test_admin_api_key_is_tenant_scoped_across_the_entire_media_data_plane(client):
    owner_name, owner_token = new_user(client)
    admin_token = login(client, "admin", "admin-pass")
    _, admin_key = _new_key(client, admin_token, "tenant-scoped-admin-key")
    key_headers = {"X-API-Key": admin_key}

    personal_image = upload(
        client, owner_token, filename="foreign-private.png", data={"visibility": "private"}
    ).json()
    _, personal_video = upload_video(client, owner_token, visibility="private")

    pending_bytes = MP4_HEADER + b"foreign-pending-session"
    pending = init_video(
        client,
        owner_token,
        pending_bytes,
        visibility="private",
        name="foreign pending",
    )
    assert pending.status_code == 201, pending.text
    pending_id = pending.json()["upload_id"]

    team = client.post(
        "/api/teams",
        headers=auth(owner_token),
        json={"name": f"scope-team-{owner_name}"},
    ).json()
    team_id = team["id"]
    team_image = upload(
        client,
        owner_token,
        filename="team-private.png",
        data={"visibility": "private", "team_id": str(team_id)},
    ).json()
    _, team_video = upload_video(
        client, owner_token, visibility="private", team_id=team_id
    )

    # An administrator's API key has no global personal or team override.
    image_list = client.get("/api/images", headers=key_headers)
    video_list = client.get("/api/videos", headers=key_headers)
    assert personal_image["code"] not in {item["code"] for item in image_list.json()["items"]}
    assert personal_video["code"] not in {item["code"] for item in video_list.json()["items"]}
    assert client.get("/api/images?scope=all", headers=key_headers).status_code == 403
    assert client.get("/api/videos?scope=all", headers=key_headers).status_code == 403
    for path in (
        f"/i/{personal_image['code']}",
        f"/v/{personal_video['code']}",
        f"/api/media/{personal_image['code']}",
        f"/api/media/{personal_image['code']}/link",
        f"/api/images/{personal_image['code']}/link",
        f"/api/videos/{personal_video['code']}/link",
        f"/i/{team_image['code']}",
        f"/v/{team_video['code']}",
        f"/api/media/{team_image['code']}",
        f"/api/media/{team_video['code']}/link",
        f"/api/images/{team_image['code']}/link",
        f"/api/videos/{team_video['code']}/link",
        f"/api/teams/{team_id}/images",
        f"/api/teams/{team_id}/videos",
        f"/api/video-uploads/{pending_id}",
    ):
        assert client.get(path, headers=key_headers).status_code == 404, path

    assert client.patch(
        f"/api/images/{personal_image['code']}",
        headers=key_headers,
        json={"name": "must not change"},
    ).status_code == 403
    assert client.patch(
        f"/api/videos/{personal_video['code']}",
        headers=key_headers,
        json={"name": "must not change"},
    ).status_code == 403
    assert client.delete(
        f"/api/images/{personal_image['code']}", headers=key_headers
    ).status_code == 403
    assert client.delete(
        f"/api/videos/{personal_video['code']}", headers=key_headers
    ).status_code == 403
    assert client.patch(
        f"/api/images/{team_image['code']}",
        headers=key_headers,
        json={"name": "must not change"},
    ).status_code == 403
    assert client.delete(
        f"/api/videos/{team_video['code']}", headers=key_headers
    ).status_code == 403

    foreign_part = put_video_part(
        client,
        admin_key,
        pending_id,
        0,
        pending_bytes,
        0,
        len(pending_bytes),
    )
    assert foreign_part.status_code == 404
    assert client.post(
        f"/api/video-uploads/{pending_id}/complete", headers=key_headers
    ).status_code == 404
    assert client.delete(
        f"/api/video-uploads/{pending_id}", headers=key_headers
    ).status_code == 404
    assert upload(
        client, admin_key, data={"team_id": str(team_id)}
    ).status_code == 403
    assert init_video(
        client, admin_key, MP4_HEADER + b"foreign-team", team_id=team_id
    ).status_code == 403

    # JWT admin keeps the explicit global override, including after lifecycle reloads.
    assert personal_image["code"] in {
        item["code"] for item in client.get("/api/images", headers=auth(admin_token)).json()["items"]
    }
    assert personal_video["code"] in {
        item["code"] for item in client.get("/api/videos", headers=auth(admin_token)).json()["items"]
    }
    assert client.get(f"/i/{personal_image['code']}", headers=auth(admin_token)).status_code == 200
    assert client.get(f"/v/{personal_video['code']}", headers=auth(admin_token)).status_code == 200
    assert client.get(
        f"/api/teams/{team_id}/images", headers=auth(admin_token)
    ).status_code == 200
    assert client.get(
        f"/api/video-uploads/{pending_id}", headers=auth(admin_token)
    ).status_code == 200
    assert client.patch(
        f"/api/images/{personal_image['code']}",
        headers=auth(admin_token),
        json={"name": "jwt admin update"},
    ).status_code == 200
    assert client.patch(
        f"/api/videos/{personal_video['code']}",
        headers=auth(admin_token),
        json={"name": "jwt admin video update"},
    ).status_code == 200

    # The same API key works for its own tenant data.
    own_image = upload(
        client, admin_key, filename="admin-owned.png", data={"visibility": "private"}
    )
    assert own_image.status_code == 201, own_image.text
    own_code = own_image.json()["code"]
    assert client.get(f"/i/{own_code}", headers=key_headers).status_code == 200
    assert client.patch(
        f"/api/images/{own_code}", headers=key_headers, json={"name": "own update"}
    ).status_code == 200
    _, own_video = upload_video(client, admin_key, visibility="private")
    assert client.get(f"/v/{own_video['code']}", headers=key_headers).status_code == 200
    assert client.patch(
        f"/api/videos/{own_video['code']}",
        headers=key_headers,
        json={"name": "own video update"},
    ).status_code == 200

    own_pending = init_video(client, admin_key, MP4_HEADER + b"admin-own-pending")
    assert own_pending.status_code == 201, own_pending.text
    own_pending_id = own_pending.json()["upload_id"]
    assert client.get(f"/api/video-uploads/{own_pending_id}", headers=key_headers).status_code == 200
    assert client.delete(f"/api/video-uploads/{own_pending_id}", headers=key_headers).status_code == 204

    # Membership, not the account's global role, unlocks shared team data.
    added = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": "admin"},
    )
    assert added.status_code == 201, added.text
    assert client.get(f"/api/teams/{team_id}/images", headers=key_headers).status_code == 200
    assert client.get(f"/api/teams/{team_id}/videos", headers=key_headers).status_code == 200
    assert client.get(f"/i/{team_image['code']}", headers=key_headers).status_code == 200
    assert client.get(f"/v/{team_video['code']}", headers=key_headers).status_code == 200
    assert upload(client, admin_key, data={"team_id": str(team_id)}).status_code == 201

    # JWT admin cleanup proves its global session override remains intact.
    assert client.delete(
        f"/api/video-uploads/{pending_id}", headers=auth(admin_token)
    ).status_code == 204
