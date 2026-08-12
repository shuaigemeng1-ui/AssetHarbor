"""Admin interface & RBAC: stats, user management, team overview, full visibility."""

from conftest import auth, login, new_user, upload


def test_admin_sees_all_images_with_owner(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    mine = upload(client, token, data={"name": "admin-can-see"}).json()["code"]

    items = client.get("/api/images?limit=100", headers=auth(atoken)).json()["items"]
    info = next(i for i in items if i["code"] == mine)
    assert info["owner_username"]  # owner info exposed to admins


def test_admin_users_endpoint(client):
    atoken = login(client, "admin", "admin-pass")
    _, utoken = new_user(client)

    resp = client.get("/api/users", headers=auth(atoken))
    assert resp.status_code == 200
    usernames = {u["username"] for u in resp.json()}
    assert "admin" in usernames

    assert client.get("/api/users", headers=auth(utoken)).status_code == 403
    assert client.get("/api/users").status_code == 401


def test_admin_stats(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    upload(client, token)
    resp = client.get("/api/admin/stats", headers=auth(atoken))
    assert resp.status_code == 200
    body = resp.json()
    assert body["users"] >= 2
    assert body["images"] >= 1
    assert body["storage_bytes"] > 0


def test_admin_stats_forbidden_for_users(client):
    _, token = new_user(client)
    assert client.get("/api/admin/stats", headers=auth(token)).status_code == 403


def test_admin_teams_overview(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    tid = client.post("/api/teams", headers=auth(token), json={"name": "visible-team"}).json()["id"]

    teams = client.get("/api/admin/teams", headers=auth(atoken)).json()
    info = next(t for t in teams if t["id"] == tid)
    assert info["member_count"] == 1
    assert info["owner_username"]


def test_admin_set_user_role(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    uid = client.get("/api/auth/me", headers=auth(token)).json()["id"]

    # 提升为 admin
    resp = client.patch(f"/api/admin/users/{uid}/role", headers=auth(atoken), json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    # 现在该用户能访问 admin 接口
    assert client.get("/api/admin/stats", headers=auth(token)).status_code == 200

    # 降回 user
    assert client.patch(f"/api/admin/users/{uid}/role", headers=auth(atoken), json={"role": "user"}).status_code == 200
    assert client.get("/api/admin/stats", headers=auth(token)).status_code == 403

    # 不能改自己的角色
    admin_me = client.get("/api/auth/me", headers=auth(atoken)).json()
    assert client.patch(f"/api/admin/users/{admin_me['id']}/role", headers=auth(atoken), json={"role": "user"}).status_code == 400
