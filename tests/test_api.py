"""API tests for upload + short-code image serving."""

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
    resp = client.get("/")
    assert resp.status_code == 200
    assert "oss" in resp.text
