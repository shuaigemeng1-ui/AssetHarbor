"""API keys: shown once, hashed storage, auth for upload/download/delete, rotate, revoke."""

from conftest import FAKE_PNG, auth, new_user, upload

from sqlalchemy import text

from app.core.database import engine
from app.models import RuntimeCounter


def test_api_key_created_once_and_listed_by_prefix(client):
    _, token = new_user(client)
    h = auth(token)

    created = client.post("/api/keys", headers=h, json={"name": "我的脚本"}).json()
    assert created["name"] == "我的脚本"
    assert len(created["key"]) > 30
    assert created["key"].startswith(created["key_prefix"])

    # 列表只含前缀，绝不含完整 key
    keys = client.get("/api/keys", headers=h).json()
    assert len(keys) == 1
    assert keys[0]["key_prefix"] == created["key_prefix"]
    assert "key" not in keys[0]
    assert all(created["key"] not in str(k) for k in keys)


def test_api_key_can_upload_list_and_delete(client):
    _, token = new_user(client)
    key = client.post("/api/keys", headers=auth(token)).json()["key"]
    kh = {"X-API-Key": key}

    # 上传
    up = client.post("/api/upload", headers=kh, files={"file": ("a.png", FAKE_PNG, "image/png")})
    assert up.status_code == 201
    code = up.json()["code"]

    # 列表
    assert client.get("/api/images", headers=kh).status_code == 200

    # 下载
    resp = client.get(f"/i/{code}", headers=kh)
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG

    # 删除
    assert client.delete(f"/api/images/{code}", headers=kh).status_code == 204
    assert client.get(f"/api/images", headers=kh).json()["total"] == 0


def test_api_key_bearer_auth_also_works(client):
    _, token = new_user(client)
    key = client.post("/api/keys", headers=auth(token)).json()["key"]
    # Authorization: Bearer <key> 同样被识别
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {key}"})
    assert resp.status_code == 200


def test_api_key_rotate_revokes_old(client):
    _, token = new_user(client)
    h = auth(token)
    old_key = client.post("/api/keys", headers=h, json={"name": "rot"}).json()["key"]
    kid = client.get("/api/keys", headers=h).json()[0]["id"]

    new = client.post(f"/api/keys/{kid}/rotate", headers=h).json()
    assert new["key"] != old_key

    # 旧 key 立即失效
    assert client.get("/api/auth/me", headers={"X-API-Key": old_key}).status_code == 401
    # 新 key 生效
    assert client.get("/api/auth/me", headers={"X-API-Key": new["key"]}).status_code == 200


def test_api_key_revoke(client):
    _, token = new_user(client)
    h = auth(token)
    key = client.post("/api/keys", headers=h).json()["key"]
    kid = client.get("/api/keys", headers=h).json()[0]["id"]

    assert client.delete(f"/api/keys/{kid}", headers=h).status_code == 204
    assert client.get("/api/auth/me", headers={"X-API-Key": key}).status_code == 401


def test_revoked_key_id_is_never_reused_or_deleted_by_a_stale_retry(client):
    _, token = new_user(client)
    headers = auth(token)
    first = client.post("/api/keys", headers=headers).json()
    assert client.delete(f"/api/keys/{first['id']}", headers=headers).status_code == 204

    replacement = client.post("/api/keys", headers=headers).json()
    assert replacement["id"] > first["id"]
    assert client.delete(f"/api/keys/{first['id']}", headers=headers).status_code == 404
    assert client.get(
        "/api/auth/me", headers={"X-API-Key": replacement["key"]}
    ).status_code == 200


def test_runtime_counter_table_has_no_foreign_keys_and_chinese_comments(client):
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA foreign_key_list(runtime_counters)")).all() == []
    assert all(
        column.comment and any("\u4e00" <= char <= "\u9fff" for char in column.comment)
        for column in RuntimeCounter.__table__.columns
    )


def test_api_keys_are_unique(client):
    _, token = new_user(client)
    h = auth(token)
    k1 = client.post("/api/keys", headers=h).json()["key"]
    k2 = client.post("/api/keys", headers=h).json()["key"]
    assert k1 != k2
    keys = client.get("/api/keys", headers=h).json()
    prefixes = [k["key_prefix"] for k in keys]
    assert len(prefixes) == len(set(prefixes))


def test_api_key_mutations_have_a_daily_per_account_limit(client, monkeypatch):
    from app.core.config import settings
    import app.services.ratelimit as ratelimit

    _, token = new_user(client)
    monkeypatch.setattr(settings, "api_key_mutation_rate_limit_per_day", 2)
    first = client.post("/api/keys", headers=auth(token))
    second = client.post("/api/keys", headers=auth(token))
    rejected = client.post("/api/keys", headers=auth(token))
    assert first.status_code == 201
    assert second.status_code == 201
    assert rejected.status_code == 429
    assert int(rejected.headers["retry-after"]) > 0

    # The shared limiter must retain a 24-hour window beyond its old one-hour
    # pruning horizon; otherwise key churn can grow traffic dimensions again.
    original_monotonic = ratelimit.time.monotonic
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: original_monotonic() + 3601)
    assert client.post("/api/keys", headers=auth(token)).status_code == 429


def test_api_key_cannot_access_others_resources(client):
    _, t1 = new_user(client)
    _, t2 = new_user(client)
    key1 = client.post("/api/keys", headers=auth(t1)).json()["key"]
    code = upload(client, t2, data={"visibility": "private"}).json()["code"]

    # key1 访问 t2 的私密图 → 404
    assert client.get(f"/i/{code}", headers={"X-API-Key": key1}).status_code == 404
    # key1 删 t2 的图 → 403
    assert client.delete(f"/api/images/{code}", headers={"X-API-Key": key1}).status_code == 403
