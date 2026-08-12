"""Teams: lifecycle, membership management, team space isolation."""

from conftest import FAKE_PNG, auth, new_user


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
    _, otoken = new_user(client)
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
