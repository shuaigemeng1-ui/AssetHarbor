"""P0 security: team asset ownership, share revocation, no-FK schema gate."""

from sqlalchemy import inspect, text
from sqlalchemy import create_engine

from app.core.database import SessionLocal, engine
from app.models import (
    ApiKey,
    Image,
    MediaGroup,
    MediaGroupItem,
    RuntimeCounter,
    Team,
    TeamMember,
    TrafficDaily,
    UploadPart,
    UploadSession,
    User,
)
from conftest import (
    FAKE_PNG,
    MP4_HEADER,
    _uname,
    auth,
    init_video,
    login,
    new_user,
    put_video_part,
    signed_link,
    upload,
    upload_video,
    url_path,
)


def _create_team_with_member(client, owner_token, member_name):
    team = client.post(
        "/api/teams",
        headers=auth(owner_token),
        json={"name": f"p0-team-{_uname('t')}"},
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    membership = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    )
    assert membership.status_code == 201, membership.text
    return team_id, membership.json()["id"]


def test_removed_member_loses_all_team_asset_access(client):
    _, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    team_id, membership_id = _create_team_with_member(client, owner_token, member_name)
    owner_headers, member_headers = auth(owner_token), auth(member_token)

    image = upload(
        client,
        member_token,
        data={"team_id": str(team_id), "visibility": "private", "name": "p0-team-image"},
    ).json()
    _init, video = upload_video(
        client,
        member_token,
        data=MP4_HEADER + b"p0-team-video",
        visibility="private",
        team_id=team_id,
        name="p0-team-video",
    )
    pending = init_video(
        client,
        member_token,
        MP4_HEADER + b"p0-pending",
        team_id=team_id,
    ).json()
    pending_id = pending["upload_id"]

    # A member API key must also lose team access after removal.
    key = client.post("/api/keys", headers=member_headers).json()["key"]
    key_headers = {"X-API-Key": key}

    # Sanity: before removal the uploader/member can access and manage.
    assert client.get(f"/i/{image['code']}", headers=member_headers).status_code == 200
    assert client.get(f"/v/{video['code']}", headers=member_headers).status_code == 200

    removed = client.delete(
        f"/api/teams/{team_id}/members/{membership_id}", headers=owner_headers
    )
    assert removed.status_code == 204

    # JWT: private team assets become invisible through short-code URLs.
    assert client.get(f"/i/{image['code']}", headers=member_headers).status_code == 404
    assert client.get(f"/v/{video['code']}", headers=member_headers).status_code == 404
    # Metadata and link endpoints hide the asset.
    assert client.get(f"/api/media/{image['code']}", headers=member_headers).status_code == 404
    assert client.get(f"/api/media/{image['code']}/link", headers=member_headers).status_code == 404
    assert client.get(f"/api/images/{image['code']}/link", headers=member_headers).status_code == 404
    assert client.get(f"/api/videos/{video['code']}/link", headers=member_headers).status_code == 404
    # Mutations are rejected (not merely hidden).
    assert client.patch(
        f"/api/images/{image['code']}", headers=member_headers, json={"name": "nope"}
    ).status_code == 403
    assert client.delete(
        f"/api/videos/{video['code']}", headers=member_headers
    ).status_code == 403
    # Pending team upload sessions are no longer manageable.
    assert client.get(
        f"/api/video-uploads/{pending_id}", headers=member_headers
    ).status_code == 403
    assert client.delete(
        f"/api/video-uploads/{pending_id}", headers=member_headers
    ).status_code == 403
    assert put_video_part(
        client, member_token, pending_id, 0, MP4_HEADER + b"p0-pending", 0, len(MP4_HEADER + b"p0-pending")
    ).status_code == 403

    # API Key: same revocation is enforced.
    assert client.get(f"/i/{image['code']}", headers=key_headers).status_code == 404
    assert client.get(f"/v/{video['code']}", headers=key_headers).status_code == 404
    assert client.get(
        f"/api/images/{image['code']}/link", headers=key_headers
    ).status_code == 404
    assert client.patch(
        f"/api/images/{image['code']}", headers=key_headers, json={"name": "nope"}
    ).status_code == 403

    # The team owner keeps full access.
    assert client.get(f"/i/{image['code']}", headers=owner_headers).status_code == 200
    assert client.get(f"/v/{video['code']}", headers=owner_headers).status_code == 200


def test_admin_delete_user_preserves_and_transfers_team_media(client):
    admin_token = login(client, "admin", "admin-pass")
    owner_name, owner_token = new_user(client)
    victim_name, victim_token = new_user(client)
    team_id, _membership_id = _create_team_with_member(client, owner_token, victim_name)
    owner_headers = auth(owner_token)

    personal = upload(client, victim_token, name="personal-will-die").json()
    team_image = upload(
        client,
        victim_token,
        data={"team_id": str(team_id), "visibility": "private", "name": "team-survives"},
    ).json()
    _init, team_video = upload_video(
        client,
        victim_token,
        data=MP4_HEADER + b"team-video-survives",
        visibility="private",
        team_id=team_id,
    )
    pending = init_video(
        client,
        victim_token,
        MP4_HEADER + b"pending-team-survives",
        team_id=team_id,
    ).json()
    pending_id = pending["upload_id"]

    victim_id = client.get("/api/auth/me", headers=auth(victim_token)).json()["id"]
    owner_id = client.get("/api/auth/me", headers=owner_headers).json()["id"]
    assert client.delete(
        f"/api/admin/users/{victim_id}", headers=auth(admin_token)
    ).status_code == 204

    # Personal media is deleted with the account.
    assert client.get(f"/i/{personal['code']}").status_code == 404



    # Team media remains, is still team-scoped, and is attributed to the team owner.
    assert client.get(f"/i/{team_image['code']}", headers=owner_headers).status_code == 200
    assert client.get(f"/v/{team_video['code']}", headers=owner_headers).status_code == 200
    image_meta = client.get(f"/api/media/{team_image['code']}", headers=owner_headers).json()
    assert image_meta["team_id"] == team_id
    assert image_meta["owner_id"] == owner_id
    video_meta = client.get(f"/api/media/{team_video['code']}", headers=owner_headers).json()
    assert video_meta["team_id"] == team_id
    assert video_meta["owner_id"] == owner_id

    # Pending team upload sessions are transferred, not cancelled.
    status = client.get(f"/api/video-uploads/{pending_id}", headers=owner_headers)
    assert status.status_code == 200, status.text

    # The team itself is preserved.
    assert client.get(f"/api/teams/{team_id}", headers=owner_headers).status_code == 200


def test_team_member_removal_keeps_existing_signed_link_until_revoked(client):
    """成员退出不追溯撤销已签发链接；显式撤销全部链接才使其失效。"""
    _, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    team_id, membership_id = _create_team_with_member(client, owner_token, member_name)
    owner_headers, member_headers = auth(owner_token), auth(member_token)

    image = upload(
        client,
        member_token,
        data={"team_id": str(team_id), "visibility": "private", "name": "signed-before-leave"},
    ).json()
    old_path = "/" + url_path(signed_link(client, member_token, image["code"])["url"])
    assert client.get(old_path).status_code == 200

    removed = client.delete(
        f"/api/teams/{team_id}/members/{membership_id}", headers=owner_headers
    )
    assert removed.status_code == 204

    # Direct JWT/team access is revoked immediately...
    assert client.get(f"/i/{image['code']}", headers=member_headers).status_code == 404
    # ...but the bearer signed link keeps its TTL contract.
    assert client.get(old_path).status_code == 200

    # Explicit "revoke all historical links" kills even the pre-removal link.
    assert client.post(
        f"/api/media/{image['code']}/revoke-links", headers=owner_headers
    ).status_code == 200
    assert client.get(old_path).status_code == 404


def test_revoke_media_links_invalidates_all_historical_signed_urls(client):
    _, token = new_user(client)
    headers = auth(token)

    image = upload(client, token, data={"visibility": "private"}).json()
    old_image_path = "/" + url_path(signed_link(client, token, image["code"])["url"])
    assert client.get(old_image_path).status_code == 200
    revoked = client.post(
        f"/api/media/{image['code']}/revoke-links", headers=headers
    )
    assert revoked.status_code == 200, revoked.text
    assert client.get(old_image_path).status_code == 404
    new_image_path = "/" + url_path(signed_link(client, token, image["code"])["url"])
    assert client.get(new_image_path).status_code == 200

    _, video = upload_video(client, token, data=MP4_HEADER + b"revoke-video", visibility="private")
    old_video_path = "/" + url_path(
        client.get(f"/api/videos/{video['code']}/link", headers=headers).json()["url"]
    )
    assert client.get(old_video_path).status_code == 200
    assert client.post(
        f"/api/media/{video['code']}/revoke-links", headers=headers
    ).status_code == 200
    assert client.get(old_video_path).status_code == 404
    new_video_path = "/" + url_path(
        client.get(f"/api/videos/{video['code']}/link", headers=headers).json()["url"]
    )
    assert client.get(new_video_path).status_code == 200

    # Another user cannot revoke someone else's links.
    _, other_token = new_user(client)
    other_image = upload(client, other_token, data={"visibility": "private"}).json()
    assert client.post(
        f"/api/media/{other_image['code']}/revoke-links", headers=headers
    ).status_code == 403


def test_all_tables_have_no_foreign_keys_and_model_comments(client):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert tables, "expected the application schema to be initialized"

    for table_name in tables:
        with engine.connect() as conn:
            fks = conn.execute(text(f"PRAGMA foreign_key_list({table_name})")).all()
        assert fks == [], f"table {table_name} still declares foreign keys: {fks}"

    models = [
        User,
        Team,
        TeamMember,
        Image,
        ApiKey,
        MediaGroup,
        MediaGroupItem,
        TrafficDaily,
        UploadSession,
        UploadPart,
        RuntimeCounter,
    ]
    for model in models:
        assert all(
            column.comment for column in model.__table__.columns
        ), f"{model.__tablename__} has columns without Chinese comments"


def test_migration_removes_foreign_keys_from_legacy_table(tmp_path, monkeypatch):
    from app.core import database

    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy-fk.db'}")
    with legacy_engine.begin() as conn:
        conn.execute(text("CREATE TABLE images (id INTEGER PRIMARY KEY, code VARCHAR(32))"))
        conn.execute(
            text(
                """
                CREATE TABLE teams (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(64) NOT NULL UNIQUE,
                    description VARCHAR(255) NOT NULL DEFAULT '',
                    owner_id INTEGER NOT NULL REFERENCES users(id),
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO teams (id, name, description, owner_id, created_at)
                VALUES (1, 'legacy-team', '', 42, '2026-01-01 00:00:00')
                """
            )
        )

    monkeypatch.setattr(database, "engine", legacy_engine)
    database._migrate()
    database._migrate()

    with legacy_engine.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_key_list(teams)")).all() == []
        row = conn.execute(
            text("SELECT id, name, owner_id FROM teams WHERE id = 1")
        ).one()
        assert tuple(row) == (1, "legacy-team", 42)
        assert conn.execute(
            text("SELECT version FROM schema_migrations ORDER BY version")
        ).scalars().all() == [1, 2]
