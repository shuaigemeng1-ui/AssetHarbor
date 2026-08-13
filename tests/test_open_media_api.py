"""开放接口：默认公开契约及 JWT/API Key/匿名隔离矩阵。"""

from conftest import FAKE_PNG, auth, login, new_user, video_fingerprint

from app.core.config import settings
from app.services.ratelimit import _LOCK, _WINDOWS


def _key(client, token, name="automation"):
    return client.post("/api/keys", headers=auth(token), json={"name": name}).json()["key"]


def _image(client, headers, *, visibility=None, team_id=None):
    data = {}
    if visibility is not None:
        data["visibility"] = visibility
    if team_id is not None:
        data["team_id"] = str(team_id)
    return client.post(
        "/api/upload",
        headers=headers,
        data=data or None,
        files={"file": ("open.png", FAKE_PNG, "image/png")},
    )


def _video_init(client, headers, *, visibility_marker="omitted"):
    data = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00mp41mp42payload"
    payload = {
        "filename": "open.mp4",
        "size": len(data),
        "name": "open video",
        "team_id": None,
        "fingerprint": video_fingerprint(data),
    }
    if visibility_marker != "omitted":
        payload["visibility"] = visibility_marker
    return client.post("/api/video-uploads", headers=headers, json=payload)


def test_omitted_visibility_is_public_for_jwt_and_api_key(client):
    """API omission is a fixed public contract for every supported credential."""
    _, token = new_user(client)
    key_headers = {"X-API-Key": _key(client, token)}

    for headers in (auth(token), key_headers):
        image = _image(client, headers)
        assert image.status_code == 201, image.text
        assert image.json()["visibility"] == "public"
        assert client.get(f"/i/{image.json()['code']}").status_code == 200

        video = _video_init(client, headers)
        assert video.status_code == 201, video.text
        assert video.json()["visibility"] == "public"


def test_explicit_private_is_preserved_for_jwt_and_api_key(client):
    _, token = new_user(client)
    key_headers = {"Authorization": f"Bearer {_key(client, token)}"}
    for headers in (auth(token), key_headers):
        image = _image(client, headers, visibility="private")
        assert image.status_code == 201
        assert image.json()["visibility"] == "private"
        assert client.get(f"/i/{image.json()['code']}").status_code == 404
        video = _video_init(client, headers, visibility_marker="private")
        assert video.status_code == 201
        assert video.json()["visibility"] == "private"


def test_unified_media_metadata_and_link_isolation(client):
    _, owner_token = new_user(client)
    _, outsider_token = new_user(client)
    owner_key = _key(client, owner_token, "owner")
    outsider_key = _key(client, outsider_token, "outsider")
    admin_token = login(client, "admin", "admin-pass")

    public_code = _image(client, auth(owner_token)).json()["code"]
    private_code = _image(client, auth(owner_token), visibility="private").json()["code"]

    # Anonymous public metadata intentionally hides tenant identifiers.
    public_anon = client.get(f"/api/media/{public_code}")
    assert public_anon.status_code == 200
    assert public_anon.json()["owner_id"] is None
    assert public_anon.json()["owner_username"] is None
    assert public_anon.json()["team_id"] is None
    assert public_anon.json()["original_filename"] is None

    # Public canonical links are open and contain no signing secret.
    public_link = client.get(f"/api/media/{public_code}/link")
    assert public_link.status_code == 200
    assert public_link.json()["url"].endswith(f"/i/{public_code}")
    assert public_link.json()["expires_at"] is None

    # Private existence is hidden from anonymous and every unrelated identity.
    assert client.get(f"/api/media/{private_code}").status_code == 404
    assert client.get(
        f"/api/media/{private_code}", headers=auth(outsider_token)
    ).status_code == 404
    assert client.get(
        f"/api/media/{private_code}", headers={"X-API-Key": outsider_key}
    ).status_code == 404

    for headers in (
        auth(owner_token),
        {"X-API-Key": owner_key},
        auth(admin_token),
    ):
        metadata = client.get(f"/api/media/{private_code}", headers=headers)
        assert metadata.status_code == 200
        assert metadata.json()["owner_id"] is not None
        signed = client.get(f"/api/media/{private_code}/link?ttl=60", headers=headers)
        assert signed.status_code == 200
        assert "expires=" in signed.json()["url"]
        assert signed.json()["expires_at"] is not None


def test_private_team_media_visible_to_team_jwt_and_api_key_only(client):
    _, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    _, outsider_token = new_user(client)
    team_id = client.post(
        "/api/teams", headers=auth(owner_token), json={"name": "open-api-team"}
    ).json()["id"]
    client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    )
    code = _image(
        client, auth(owner_token), visibility="private", team_id=team_id
    ).json()["code"]
    member_key = _key(client, member_token, "team-member")

    assert client.get(f"/api/media/{code}", headers=auth(member_token)).status_code == 200
    assert client.get(
        f"/api/media/{code}/link", headers={"X-API-Key": member_key}
    ).status_code == 200
    assert client.get(f"/api/media/{code}", headers=auth(outsider_token)).status_code == 404


def test_anonymous_unified_media_lookups_are_rate_limited_before_database(client, monkeypatch):
    _, token = new_user(client)
    code = _image(client, auth(token)).json()["code"]
    monkeypatch.setattr(settings, "images_rate_limit_per_minute", 1)
    with _LOCK:
        _WINDOWS.clear()
    assert client.get(f"/api/media/{code}").status_code == 200
    assert client.get(f"/api/media/{'z' * len(code)}").status_code == 429
