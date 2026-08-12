"""Upload: auth requirement, naming, visibility, limits."""

from conftest import FAKE_PNG, PNG_MAGIC, auth, new_user, upload


def test_upload_requires_auth(client):
    resp = client.post("/api/upload", files={"file": ("a.png", FAKE_PNG, "image/png")})
    assert resp.status_code == 401


def test_upload_with_custom_name_and_visibility(client):
    _, token = new_user(client)
    resp = client.post(
        "/api/upload",
        headers=auth(token),
        data={"name": "我的封面", "visibility": "private"},
        files={"file": ("original.png", FAKE_PNG, "image/png")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "我的封面"
    assert body["visibility"] == "private"
    assert body["owner_id"] is not None
    assert body["url"].endswith(f"/i/{body['code']}")


def test_upload_name_falls_back_to_filename(client):
    _, token = new_user(client)
    body = upload(client, token, filename="my-photo.png").json()
    assert body["name"] == "my-photo.png"


def test_upload_invalid_visibility(client):
    _, token = new_user(client)
    resp = client.post(
        "/api/upload",
        headers=auth(token),
        data={"visibility": "sneaky"},
        files={"file": ("a.png", FAKE_PNG, "image/png")},
    )
    assert resp.status_code == 422


def test_upload_rejects_non_image(client):
    _, token = new_user(client)
    resp = client.post(
        "/api/upload", headers=auth(token), files={"file": ("x.txt", b"hello world", "text/plain")}
    )
    assert resp.status_code == 415


def test_upload_enforces_size_limit(client):
    _, token = new_user(client)
    over = PNG_MAGIC + b"\x00" * (1024 * 1024 + 1)  # 1 byte over the 1 MB test limit
    resp = client.post("/api/upload", headers=auth(token), files={"file": ("big.png", over, "image/png")})
    assert resp.status_code == 413


def test_upload_rate_limited_per_user(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "upload_rate_limit_per_minute", 2)
    _, token = new_user(client)
    statuses = [upload(client, token).status_code for _ in range(4)]
    assert statuses[-1] == 429
