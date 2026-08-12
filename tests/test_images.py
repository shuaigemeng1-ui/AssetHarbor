"""Image serving: visibility enforcement, signed URLs, deletion, fetch rate limit."""

import re

from conftest import FAKE_PNG, SVG, auth, login, new_user, signed_link, upload, url_path


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
    assert img.headers["content-security-policy"] == "sandbox; default-src 'none'"


# --- signed URLs -----------------------------------------------------------


def test_signed_link_owner_can_generate(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    body = signed_link(client, token, code)
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
    path = url_path(signed_link(client, token, code)["url"])
    resp = client.get(f"/{path}")
    assert resp.status_code == 200
    assert resp.content == FAKE_PNG


def test_forged_signature_rejected(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    path = url_path(signed_link(client, token, code)["url"])
    forged = path.replace("sig=", "sig=AAAA")
    assert client.get(f"/{forged}").status_code == 404


def test_expired_signature_rejected(client):
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    path = url_path(signed_link(client, token, code)["url"])
    # expires 改为过去的时间戳，sig 不变 → 必须拒绝
    path = re.sub(r"expires=\d+", "expires=1", path)
    assert client.get(f"/{path}").status_code == 404


def test_signature_bound_to_one_code(client):
    _, token = new_user(client)
    code1 = upload(client, token, data={"visibility": "private"}).json()["code"]
    code2 = upload(client, token, data={"visibility": "private", "name": "second"}).json()["code"]
    path = url_path(signed_link(client, token, code1)["url"])
    swapped = path.replace(code1, code2, 1)  # sig 属于 code1，换到 code2 → 拒绝
    assert client.get(f"/{swapped}").status_code == 404


def test_admin_signed_link_for_others(client):
    atoken = login(client, "admin", "admin-pass")
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]
    body = signed_link(client, atoken, code)
    path = url_path(body["url"])
    assert client.get(f"/{path}").status_code == 200


def test_public_image_needs_no_signed_url(client):
    """公开图仍保持"任何人可访问"的语义，不被签名机制误伤。"""
    _, token = new_user(client)
    code = upload(client, token, data={"visibility": "public"}).json()["code"]
    assert client.get(f"/i/{code}").status_code == 200


# --- deletion --------------------------------------------------------------


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


# --- update (PATCH) --------------------------------------------------------


def test_patch_visibility_owner(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token).json()["code"]  # test env default is public

    r = client.patch(f"/api/images/{code}", headers=h, json={"visibility": "private"})
    assert r.status_code == 200
    assert r.json()["visibility"] == "private"
    # 改私密后匿名访问 404
    assert client.get(f"/i/{code}").status_code == 404

    # 改回公开后任何人可访问
    assert client.patch(f"/api/images/{code}", headers=h, json={"visibility": "public"}).status_code == 200
    assert client.get(f"/i/{code}").status_code == 200


def test_patch_name(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token).json()["code"]
    r = client.patch(f"/api/images/{code}", headers=h, json={"name": "新名字"})
    assert r.status_code == 200
    assert r.json()["name"] == "新名字"


def test_patch_visibility_forbidden_for_others(client):
    _, t1 = new_user(client)
    _, t2 = new_user(client)
    code = upload(client, t1).json()["code"]
    assert client.patch(f"/api/images/{code}", headers=auth(t2), json={"visibility": "private"}).status_code == 403
    assert client.patch(f"/api/images/{code}", json={"visibility": "private"}).status_code == 401


def test_patch_invalid_visibility(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token).json()["code"]
    assert client.patch(f"/api/images/{code}", headers=h, json={"visibility": "sneaky"}).status_code == 422


# --- cache control & link revocation ---------------------------------------


def test_private_image_not_cached(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token, data={"visibility": "private"}).json()["code"]

    resp = client.get(f"/i/{code}", headers=h)
    assert resp.status_code == 200
    assert "no-store" in resp.headers["cache-control"]
    assert "max-age=31536000" not in resp.headers["cache-control"]


def test_public_image_requires_cache_revalidation(client):
    _, token = new_user(client)
    code = upload(client, token).json()["code"]  # test env default is public
    resp = client.get(f"/i/{code}")
    assert resp.headers["cache-control"] == "public, max-age=0, must-revalidate"
    assert "immutable" not in resp.headers["cache-control"]


def test_signed_link_revoked_when_made_private(client):
    _, token = new_user(client)
    h = auth(token)
    code = upload(client, token).json()["code"]  # public

    # 公开时签发的链接（公开图也可生成）
    path = url_path(signed_link(client, token, code)["url"])
    assert client.get(f"/{path}").status_code == 200

    # 设为私密 → 旧签名链接立即失效
    client.patch(f"/api/images/{code}", headers=h, json={"visibility": "private"})
    assert client.get(f"/{path}").status_code == 404

    # 新生成的签名链接仍有效
    new_path = url_path(signed_link(client, token, code)["url"])
    assert client.get(f"/{new_path}").status_code == 200


# --- rate limit ------------------------------------------------------------


def test_image_fetch_rate_limited(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "images_rate_limit_per_minute", 5)
    _, token = new_user(client)
    code = upload(client, token).json()["code"]
    statuses = [client.get(f"/i/{code}").status_code for _ in range(8)]
    assert statuses[-1] == 429
