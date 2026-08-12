"""Auth: register, login, me, change password, login rate limiting."""

from conftest import _uname, auth, login, new_user, register


def test_register_login_me_flow(client):
    name = _uname()
    u = register(client, name)
    assert u["role"] == "user"
    token = login(client, name)
    me = client.get("/api/auth/me", headers=auth(token))
    assert me.status_code == 200
    assert me.json()["username"] == name


def test_login_wrong_password(client):
    name = _uname()
    register(client, name)
    resp = client.post("/api/auth/login", data={"username": name, "password": "wrong1"})
    assert resp.status_code == 401


def test_register_duplicate_username(client):
    name = _uname()
    register(client, name)
    resp = client.post("/api/auth/register", json={"username": name, "password": "pass123"})
    assert resp.status_code == 409


def test_register_validation(client):
    assert client.post("/api/auth/register", json={"username": "ab", "password": "pass123"}).status_code == 422
    assert client.post("/api/auth/register", json={"username": "ok-name", "password": "123"}).status_code == 422


def test_change_password_flow(client):
    name, token = new_user(client)
    h = auth(token)

    # 旧密码错误 → 400
    assert client.post("/api/auth/change-password", headers=h,
                       json={"old_password": "wrong1", "new_password": "newpass1"}).status_code == 400

    # 成功修改
    assert client.post("/api/auth/change-password", headers=h,
                       json={"old_password": "pass123", "new_password": "newpass1"}).status_code == 204

    # 旧密码登录失败，新密码成功
    assert client.post("/api/auth/login", data={"username": name, "password": "pass123"}).status_code == 401
    assert client.post("/api/auth/login", data={"username": name, "password": "newpass1"}).status_code == 200


def test_admin_reset_password(client):
    atoken = login(client, "admin", "admin-pass")
    name, token = new_user(client)
    uid = client.get("/api/auth/me", headers=auth(token)).json()["id"]

    assert client.patch(f"/api/admin/users/{uid}/password", headers=auth(atoken),
                        json={"new_password": "reset123"}).status_code == 204
    assert client.post("/api/auth/login", data={"username": name, "password": "pass123"}).status_code == 401
    assert client.post("/api/auth/login", data={"username": name, "password": "reset123"}).status_code == 200

    # 普通用户不能重置他人密码
    _, t2 = new_user(client)
    me2 = client.get("/api/auth/me", headers=auth(t2)).json()
    assert client.patch(f"/api/admin/users/{me2['id']}/password", headers=auth(t2),
                        json={"new_password": "x12345"}).status_code == 403


def test_login_rate_limited_per_username(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "login_rate_limit_per_username", 3)
    name = _uname()
    register(client, name)
    statuses = [
        client.post("/api/auth/login", data={"username": name, "password": "wrong-pass"}).status_code
        for _ in range(5)
    ]
    assert 401 in statuses          # 前几次是正常报错
    assert statuses[-1] == 429      # 超限后限速
    assert "retry-after" in client.post(
        "/api/auth/login", data={"username": name, "password": "wrong-pass"}
    ).headers
