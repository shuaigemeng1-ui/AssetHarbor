"""Gallery: per-user isolation, search, pagination, SPA serving."""

import pytest

from conftest import auth, new_user, upload


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


def test_custom_docs_page_served(client):
    from app.main import STATIC_DIR

    if not (STATIC_DIR / "docs.html").is_file():
        pytest.skip("docs page not built")
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "API" in resp.text
    assert "openapi" in resp.text.lower() or "Authorization" in resp.text
