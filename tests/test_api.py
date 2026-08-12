"""API tests: auth, RBAC, user isolation, naming, search, security."""

import itertools
import re

import pytest

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FAKE_PNG = PNG_MAGIC + b"\x00" * 64

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'

_uids = itertools.count(1)


def _uname(prefix="user"):
    return f"{prefix}{next(_uids)}"


def register(client, username, password="pass123"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client, username, password="pass123"):
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def new_user(client):
    name = _uname()
    register(client, name)
    return name, login(client, name)


def upload(client, token, filename="a.png", data=None, **extra):
    fields = dict(data or {})
    fields.update(extra)
    files = {"file": (filename, FAKE_PNG, "image/png")}
    return client.post("/api/upload", headers=auth(token), data=fields or None, files=files)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Upload: auth required + naming + visibility
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Serving + visibility enforcement
# ---------------------------------------------------------------------------


def test_public_image_anyone_can_fetch(client):
    _, token = new_user(client)
    code = upload(client, token).json()["code"]
    assert client.get(f"/i/{code}").status_code == 200
    assert client.get(f"/i/{code}").content == FAKE_PNG


def test_private_image_owner_only(client):
    _, t1 = new_user(client)
    _, t2 = new_user(client)
    code = upload(client, t1, data={"visibility": "private"}).json()["code"]

    assert client.get(f"/i/{code}", headers=auth(t1)).status_code == 200
    assert client.get(f"/i/{code}", headers=auth(t2)).status_code == 404
    assert client.get(f"/i/{code}").status_code == 404


def test_admin_can_view_any_private_image(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    assert client.get(f"/i/{code}", headers=auth(atoken)).status_code == 200


def test_unknown_code_404(client):
    assert client.get("/i/doesnotexist").status_code == 404


def test_svg_is_downloaded_not_rendered(client):
    _, token = new_user(client)
    resp = client.post(
        "/api/upload", headers=auth(token), files={"file": ("a.svg", SVG, "image/svg+xml")}
    )
    code = resp.json()["code"]
    img = client.get(f"/i/{code}")
    assert img.status_code == 200
    assert "attachment" in img.headers["content-disposition"]
    assert img.headers["x-content-type-options"] == "nosniff"


# ---------------------------------------------------------------------------
# Gallery: isolation + search
# ---------------------------------------------------------------------------


def test_gallery_requires_auth(client):
    assert client.get("/api/images").status_code == 401


def test_gallery_isolation_between_users(client):
    _, t1 = new_user(client)
    _, t2 = new_user(client)
    c1 = upload(client, t1).json()["code"]
    c2 = upload(client, t2, filename="b.png").json()["code"]

    list1 = client.get("/api/images", headers=auth(t1)).json()
    list2 = client.get("/api/images", headers=auth(t2)).json()
    codes1 = {i["code"] for i in list1["items"]}
    codes2 = {i["code"] for i in list2["items"]}
    assert c1 in codes1 and c2 not in codes1
    assert c2 in codes2 and c1 not in codes2


def test_gallery_search(client):
    _, token = new_user(client)
    h = auth(token)
    hit = upload(client, token, data={"name": "sunset-photo"}).json()["code"]
    upload(client, token, filename="b.png", data={"name": "meeting-notes"})

    res = client.get("/api/images?q=sunset", headers=h).json()
    codes = {i["code"] for i in res["items"]}
    assert hit in codes
    assert all("sunset" in (i["name"] or "") for i in res["items"])


def test_gallery_search_by_code(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token, data={"name": "whatever"}).json()["code"]

    res = client.get(f"/api/images?q={code}", headers=h).json()
    assert [i["code"] for i in res["items"]] == [code]


def test_gallery_pagination_params(client):
    _, token = new_user(client)
    h = auth(token)
    assert client.get("/api/images?limit=0", headers=h).status_code == 422
    assert client.get("/api/images?limit=101", headers=h).status_code == 422
    assert client.get("/api/images?offset=-1", headers=h).status_code == 422


def test_gallery_newest_first(client):
    _, token = new_user(client)
    h = auth(token)
    first = upload(client, token).json()["code"]
    second = upload(client, token, filename="b.png").json()["code"]
    items = client.get("/api/images?limit=2", headers=h).json()["items"]
    assert items[0]["code"] == second
    assert items[1]["code"] == first


# ---------------------------------------------------------------------------
# RBAC
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Security: signed URLs for private images
# ---------------------------------------------------------------------------


def _link(client, token, code, ttl=None):
    url = f"/api/images/{code}/link"
    if ttl:
        url += f"?ttl={ttl}"
    resp = client.get(url, headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def _url_path(url):
    """Extract the path+query from an absolute URL: /i/CODE?expires=..&sig=.."""
    return url.split("://", 1)[-1].split("/", 1)[-1]


def test_signed_link_owner_can_generate(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    body = _link(client, token, code)
    assert body["url"].startswith("http")
    assert "expires=" in body["url"] and "sig=" in body["url"]
    assert body["expires_at"]


def test_signed_link_denied_for_others(client):
    _, t1 = new_user(client)
    _, t2 = new_user(client)
    code = upload(client, t1, data={"visibility": "private"}).json()["code"]
    assert client.get(f"/api/images/{code}/link", headers=auth(t2)).status_code == 404
    assert client.get(f"/api/images/{code}/link").status_code == 401


def test_private_image_accessible_via_signed_url(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    path = _url_path(_link(client, token, code)["url"])
    resp = client.get(f"/{path}")
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG


def test_forged_signature_rejected(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    path = _url_path(_link(client, token, code)["url"])
    forged = path.replace("sig=", "sig=AAAA")
    assert client.get(f"/{forged}").status_code == 404


def test_expired_signature_rejected(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    path = _url_path(_link(client, token, code)["url"])
    # expires 改为过去的时间戳，sig 不变 → 必须拒绝
    path = re.sub(r"expires=\d+", "expires=1", path)
    assert client.get(f"/{path}").status_code == 404


def test_signature_bound_to_one_code(client):
    _, token = new_user(client)
    code1 = upload(client, token, data={"visibility": "private"}).json()["code"]
    code2 = upload(client, token, data={"visibility": "private", "name": "second"}).json()["code"]
    path = _url_path(_link(client, token, code1)["url"])
    swapped = path.replace(code1, code2, 1)  # sig 属于 code1，换到 code2 → 拒绝
    assert client.get(f"/{swapped}").status_code == 404


def test_admin_signed_link_for_others(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    body = _link(client, atoken, code)
    path = _url_path(body["url"])
    assert client.get(f"/{path}").status_code == 200


def test_public_image_needs_no_signed_url(client):
    """公开图仍保持"任何人可访问"的语义，不被签名机制误伤。"""
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "public"}).json()["code"]
    assert client.get(f"/i/{code}").status_code == 200


# ---------------------------------------------------------------------------
# Security: rate limiting
# ---------------------------------------------------------------------------


def test_login_rate_limited_per_username(client, monkeypatch):
    from app.config import settings

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


def test_image_fetch_rate_limited(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "images_rate_limit_per_minute", 5)
    _, token = new_user(client)
    code = upload(client, token).json()["code"]
    statuses = [client.get(f"/i/{code}").status_code for _ in range(8)]
    assert statuses[-1] == 429


def test_upload_rate_limited_per_user(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "upload_rate_limit_per_minute", 2)
    _, token = new_user(client)
    statuses = [upload(client, token).status_code for _ in range(4)]
    assert statuses[-1] == 429


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------


def test_team_lifecycle(client):
    _, token = new_user(client)
    h = auth(token)

    # 创建
    resp = client.post("/api/teams", headers=h, json={"name": "design-team", "description": "设计组"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "owner"
    assert body["member_count"] == 1
    tid = body["id"]

    # 列表
    teams = client.get("/api/teams", headers=h).json()
    assert [t["name"] for t in teams] == ["design-team"]

    # 详情
    detail = client.get(f"/api/teams/{tid}", headers=h).json()
    assert detail["members"][0]["username"].startswith("user")
    assert detail["members"][0]["role"] == "owner"

    # 重名 409
    assert client.post("/api/teams", headers=h, json={"name": "design-team"}).status_code == 409

    # 删除
    assert client.delete(f"/api/teams/{tid}", headers=h).status_code == 204
    assert client.get(f"/api/teams/{tid}", headers=h).status_code == 404


def test_team_membership_management(client):
    owner, otoken = new_user(client)
    other, other_name = None, None
    _, token = new_user(client)  # 将被邀请的成员
    oh = auth(otoken)
    th = auth(token)

    tid = client.post("/api/teams", headers=oh, json={"name": "team-x"}).json()["id"]

    # 非团队成员看不到团队（404）
    outsider, xtoken = new_user(client)
    assert client.get(f"/api/teams/{tid}", headers=auth(xtoken)).status_code == 404

    # 邀请成员（需要知道对方 username）
    other_name = client.get("/api/auth/me", headers=th).json()["username"]
    resp = client.post(f"/api/teams/{tid}/members", headers=oh, json={"username": other_name})
    assert resp.status_code == 201
    mid = resp.json()["id"]
    assert resp.json()["role"] == "member"

    # 成员现在能看到团队
    assert client.get(f"/api/teams/{tid}", headers=th).status_code == 200

    # 重复邀请 409
    assert client.post(f"/api/teams/{tid}/members", headers=oh, json={"username": other_name}).status_code == 409

    # 成员无权加人（403）
    assert client.post(f"/api/teams/{tid}/members", headers=th, json={"username": outsider}).status_code == 403

    # 拥有者提升成员为 admin
    r = client.patch(f"/api/teams/{tid}/members/{mid}", headers=oh, json={"role": "admin"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

    # 成员（现在是 admin）可以加人了
    outsider_name = client.get("/api/auth/me", headers=auth(xtoken)).json()["username"]
    assert client.post(f"/api/teams/{tid}/members", headers=th, json={"username": outsider_name}).status_code == 201

    # 非 owner 不能改角色（403）
    assert client.patch(f"/api/teams/{tid}/members/{mid}", headers=th, json={"role": "member"}).status_code == 403

    # 移除成员
    member = client.get(f"/api/teams/{tid}", headers=oh).json()["members"]
    target = next(m for m in member if m["role"] == "member")
    assert client.delete(f"/api/teams/{tid}/members/{target['id']}", headers=oh).status_code == 204
    # 被移除者再也看不到团队
    assert client.get(f"/api/teams/{tid}", headers=auth(xtoken)).status_code == 404


def test_team_upload_and_space(client):
    _, otoken = new_user(client)
    _, mtoken = new_user(client)
    oh, mh = auth(otoken), auth(mtoken)
    tid = client.post("/api/teams", headers=oh, json={"name": "space-team"}).json()["id"]
    member_name = client.get("/api/auth/me", headers=mh).json()["username"]
    client.post(f"/api/teams/{tid}/members", headers=oh, json={"username": member_name})

    # 成员上传到团队空间
    up = client.post(
        "/api/upload", headers=mh,
        data={"name": "team-doc", "team_id": str(tid), "visibility": "private"},
        files={"file": ("a.png", FAKE_PNG, "image/png")},
    )
    assert up.status_code == 201
    code = up.json()["code"]
    assert up.json()["team_id"] == tid

    # 团队空间列表（双方都可见）
    space = client.get(f"/api/teams/{tid}/images", headers=oh).json()
    assert space["total"] == 1 and space["items"][0]["code"] == code
    assert client.get(f"/api/teams/{tid}/images", headers=mh).json()["total"] == 1

    # 私密团队图：团队成员可访问，外部人员 404
    assert client.get(f"/i/{code}", headers=mh).status_code == 200
    outsider, xtoken = new_user(client)
    assert client.get(f"/i/{code}", headers=auth(xtoken)).status_code == 404
    assert client.get(f"/i/{code}").status_code == 404

    # 团队图不出现在个人画廊
    personal = client.get("/api/images", headers=mh).json()
    assert all(i["code"] != code for i in personal["items"])

    # 非成员无法访问团队空间（404）
    assert client.get(f"/api/teams/{tid}/images", headers=auth(xtoken)).status_code == 404

    # 非成员无法上传到团队（403）
    r = client.post(
        "/api/upload", headers=auth(xtoken),
        data={"team_id": str(tid)}, files={"file": ("a.png", FAKE_PNG, "image/png")},
    )
    assert r.status_code == 403


def test_team_delete_returns_images_to_owner(client):
    _, otoken = new_user(client)
    h = auth(otoken)
    tid = client.post("/api/teams", headers=h, json={"name": "temp-team"}).json()["id"]
    code = client.post(
        "/api/upload", headers=h, data={"team_id": str(tid)},
        files={"file": ("a.png", FAKE_PNG, "image/png")},
    ).json()["code"]

    assert client.delete(f"/api/teams/{tid}", headers=h).status_code == 204
    # 图回到上传者的个人空间
    personal = client.get("/api/images", headers=h).json()
    assert code in {i["code"] for i in personal["items"]}


# ---------------------------------------------------------------------------
# Image deletion
# ---------------------------------------------------------------------------


def test_delete_own_image(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token).json()["code"]
    assert client.delete(f"/api/images/{code}", headers=h).status_code == 204
    assert client.get(f"/i/{code}").status_code == 404


def test_delete_forbidden_for_others(client):
    _, t1 = new_user(client)
    _, t2 = new_user(client)
    code = upload(client, t1).json()["code"]
    assert client.delete(f"/api/images/{code}", headers=auth(t2)).status_code == 403
    assert client.delete(f"/api/images/{code}").status_code == 401


def test_admin_can_delete_any_image(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    code = upload(client, token).json()["code"]
    assert client.delete(f"/api/images/{code}", headers=auth(atoken)).status_code == 204


# ---------------------------------------------------------------------------
# Admin interface
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_unknown_api_route_returns_json_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")


def test_index_page_served(client):
    from app.main import STATIC_DIR

    if not (STATIC_DIR / "index.html").is_file():
        pytest.skip("frontend not built")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "oss" in resp.text


def test_spa_fallback_serves_index_for_unknown_paths(client):
    from app.main import STATIC_DIR

    if not (STATIC_DIR / "index.html").is_file():
        pytest.skip("frontend not built")
    resp = client.get("/some/client/route")
    assert resp.status_code == 200
    assert "oss" in resp.text
