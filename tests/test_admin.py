"""Admin interface & RBAC: stats, user management, team overview, full visibility."""

from conftest import _uname, auth, login, new_user, upload


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
    name, token = new_user(client)
    uid = client.get("/api/auth/me", headers=auth(token)).json()["id"]

    # 提升为 admin
    resp = client.patch(f"/api/admin/users/{uid}/role", headers=auth(atoken), json={"role": "admin"})
    assert resp.status_code == 200
    assert resp.json()["role"] == "admin"

    # 角色变化会撤销旧 JWT；重新登录后才取得新的权限。
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401
    token = login(client, name)
    assert client.get("/api/admin/stats", headers=auth(token)).status_code == 200

    # 降回 user
    assert client.patch(f"/api/admin/users/{uid}/role", headers=auth(atoken), json={"role": "user"}).status_code == 200
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401
    token = login(client, name)
    assert client.get("/api/admin/stats", headers=auth(token)).status_code == 403

    # 不能改自己的角色
    admin_me = client.get("/api/auth/me", headers=auth(atoken)).json()
    assert client.patch(f"/api/admin/users/{admin_me['id']}/role", headers=auth(atoken), json={"role": "user"}).status_code == 400


def test_admin_delete_user_removes_all_data(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    h = auth(token)

    code = upload(client, token).json()["code"]
    key = client.post("/api/keys", headers=h).json()["key"]
    team_name = f"team-of-{_uname()}"
    client.post("/api/teams", headers=h, json={"name": team_name})
    uid = client.get("/api/auth/me", headers=h).json()["id"]

    assert client.delete(f"/api/admin/users/{uid}", headers=auth(atoken)).status_code == 204

    # 账号 / 图片 / key 清理；团队资产保留并转交给执行删除的管理员。
    assert client.get("/api/auth/me", headers=h).status_code == 401
    assert client.get(f"/i/{code}").status_code == 404
    assert client.get("/api/auth/me", headers={"X-API-Key": key}).status_code == 401
    teams = client.get("/api/admin/teams", headers=auth(atoken)).json()
    retained = [t for t in teams if t["name"] == team_name]
    assert len(retained) == 1
    assert retained[0]["owner_username"] == "admin"


def test_admin_cannot_delete_self(client):
    atoken = login(client, "admin", "admin-pass")
    admin_me = client.get("/api/auth/me", headers=auth(atoken)).json()
    assert client.delete(f"/api/admin/users/{admin_me['id']}", headers=auth(atoken)).status_code == 400


def test_admin_delete_user_forbidden_for_non_admin(client):
    _, token = new_user(client)
    _, victim = new_user(client)
    vid = client.get("/api/auth/me", headers=auth(victim)).json()["id"]
    assert client.delete(f"/api/admin/users/{vid}", headers=auth(token)).status_code == 403
