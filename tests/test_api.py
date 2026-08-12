"""API tests for upload + short-code image serving."""

import pytest

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FAKE_PNG = PNG_MAGIC + b"\x00" * 64

SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'


def test_upload_and_fetch_roundtrip(client):
    resp = client.post("/api/upload", files={"file": ("a.png", FAKE_PNG, "image/png")})
    assert resp.status_code == 201
    body = resp.json()

    assert len(body["code"]) == 8
    assert body["content_type"] == "image/png"
    assert body["size"] == len(FAKE_PNG)
    assert body["url"].endswith(f"/i/{body['code']}")

    img = client.get(f"/i/{body['code']}")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/png"
    assert img.content == FAKE_PNG


def test_upload_rejects_non_image(client):
    resp = client.post("/api/upload", files={"file": ("x.txt", b"hello world", "text/plain")})
    assert resp.status_code == 415


def test_upload_rejects_empty_file(client):
    resp = client.post("/api/upload", files={"file": ("empty.png", b"", "image/png")})
    assert resp.status_code == 400


def test_upload_enforces_size_limit(client):
    over_limit = PNG_MAGIC + b"\x00" * (1024 * 1024 + 1)  # 1 byte over the 1 MB test limit
    resp = client.post("/api/upload", files={"file": ("big.png", over_limit, "image/png")})
    assert resp.status_code == 413


def test_unknown_code_returns_404(client):
    assert client.get("/i/doesnotexist").status_code == 404


def test_svg_is_downloaded_not_rendered(client):
    """SVG may carry scripts: it must be served as an attachment, never inline."""
    resp = client.post("/api/upload", files={"file": ("a.svg", SVG, "image/svg+xml")})
    assert resp.status_code == 201
    code = resp.json()["code"]

    img = client.get(f"/i/{code}")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/svg+xml"
    assert "attachment" in img.headers["content-disposition"]
    assert img.headers["x-content-type-options"] == "nosniff"


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "version": "0.1.0"}


def test_index_page_served(client):
    from app.main import STATIC_DIR

    if not (STATIC_DIR / "index.html").is_file():
        pytest.skip("frontend not built; run `npm --prefix frontend run build`")
    resp = client.get("/")
    assert resp.status_code == 200
    assert "oss" in resp.text


def test_spa_fallback_serves_index_for_unknown_paths(client):
    from app.main import STATIC_DIR

    if not (STATIC_DIR / "index.html").is_file():
        pytest.skip("frontend not built; run `npm --prefix frontend run build`")
    resp = client.get("/some/client/route")
    assert resp.status_code == 200
    assert "oss" in resp.text


def test_unknown_api_route_returns_json_404(client):
    resp = client.get("/api/nope")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")


def test_gallery_lists_uploaded_images(client):
    up = client.post("/api/upload", files={"file": ("a.png", FAKE_PNG, "image/png")})
    assert up.status_code == 201
    code = up.json()["code"]

    resp = client.get("/api/images")
    assert resp.status_code == 200
    body = resp.json()

    codes = [i["code"] for i in body["items"]]
    assert code in codes
    assert body["total"] >= 1

    info = next(i for i in body["items"] if i["code"] == code)
    assert info["url"].startswith("http")
    assert info["content_type"] == "image/png"
    assert info["original_filename"] == "a.png"
    assert info["sha256"]


def test_gallery_pagination_params(client):
    assert client.get("/api/images?limit=0").status_code == 422
    assert client.get("/api/images?limit=101").status_code == 422
    assert client.get("/api/images?offset=-1").status_code == 422
    resp = client.get("/api/images?limit=1&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) <= 1


def test_gallery_newest_first(client):
    first = client.post("/api/upload", files={"file": ("a.png", FAKE_PNG, "image/png")}).json()["code"]
    second = client.post("/api/upload", files={"file": ("b.png", FAKE_PNG, "image/png")}).json()["code"]
    body = client.get("/api/images?limit=2").json()
    assert body["items"][0]["code"] == second
    assert body["items"][1]["code"] == first
