"""Unified media library, groups, lifecycle and admin user creation."""

import threading
import time

from sqlalchemy import inspect, select

from app.core.database import SessionLocal, engine
from app.models import Image, MediaGroup, MediaGroupItem
from app.services.images import delete_image
from app.services.library import cleanup_orphan_media_library, library_lifecycle_lease
from conftest import MP4_HEADER, _uname, auth, init_video, login, new_user, upload, upload_video


def _create_group(client, token, **overrides):
    payload = {
        "name": f"group-{_uname('g')}",
        "description": "常用素材",
        "color": "#2563eb",
        "sort_order": 0,
        "team_id": None,
    }
    payload.update(overrides)
    response = client.post("/api/media-groups", headers=auth(token), json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _create_team(client, token):
    response = client.post(
        "/api/teams",
        headers=auth(token),
        json={"name": f"team-{_uname('t')}", "description": "media team"},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_personal_group_crud_mixed_media_and_unified_listing(client):
    _, token = new_user(client)
    image = upload(client, token, data={"name": "brand-mark"}).json()
    _, video = upload_video(client, token, name="launch-film")
    group = _create_group(client, token, name="Campaign", color="#AABBCC", sort_order=5)

    listed = client.get("/api/media-groups", headers=auth(token)).json()
    assert listed["total"] == 1
    assert listed["items"][0]["color"] == "#aabbcc"
    assert listed["items"][0]["item_count"] == 0

    added = client.post(
        f"/api/media-groups/{group['id']}/items",
        headers=auth(token),
        json={"codes": [image["code"], video["code"], image["code"]]},
    )
    assert added.status_code == 200, added.text
    assert added.json()["added"] == 2
    assert added.json()["skipped"] == 1
    assert added.json()["group"]["item_count"] == 2

    items = client.get(
        f"/api/media-groups/{group['id']}/items?limit=1", headers=auth(token)
    ).json()
    assert items["total"] == 2
    assert len(items["items"]) == 1
    assert items["items"][0]["media_kind"] in {"image", "video"}
    assert items["items"][0]["url"].endswith(
        (f"/i/{items['items'][0]['code']}", f"/v/{items['items'][0]['code']}")
    )

    video_items = client.get(
        f"/api/media-groups/{group['id']}/items?kind=video&q=launch",
        headers=auth(token),
    ).json()
    assert video_items["total"] == 1
    assert video_items["items"][0]["code"] == video["code"]

    unified = client.get("/api/media?kind=all&limit=100", headers=auth(token)).json()
    assert unified["total"] == 2
    assert {item["media_kind"] for item in unified["items"]} == {"image", "video"}

    patched = client.patch(
        f"/api/media-groups/{group['id']}",
        headers=auth(token),
        json={"name": "Campaign 2026", "description": "精选", "sort_order": -2},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Campaign 2026"
    assert patched.json()["sort_order"] == -2

    assert client.delete(
        f"/api/media-groups/{group['id']}/items/{image['code']}", headers=auth(token)
    ).status_code == 204
    assert client.get(
        f"/api/media-groups/{group['id']}/items", headers=auth(token)
    ).json()["total"] == 1

    assert client.delete(f"/api/media-groups/{group['id']}", headers=auth(token)).status_code == 204
    # Deleting a group never deletes its underlying media.
    assert client.get(f"/i/{image['code']}").status_code == 200
    assert client.get(f"/v/{video['code']}").status_code == 200


def test_create_group_with_codes_is_atomic(client):
    _, owner_token = new_user(client)
    _, stranger_token = new_user(client)
    owned = upload(client, owner_token).json()
    foreign = upload(client, stranger_token).json()

    created = client.post(
        "/api/media-groups",
        headers=auth(owner_token),
        json={
            "name": "Created and filled",
            "codes": [owned["code"], owned["code"]],
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["item_count"] == 1

    rejected = client.post(
        "/api/media-groups",
        headers=auth(owner_token),
        json={
            "name": "Must roll back",
            "codes": [owned["code"], foreign["code"]],
        },
    )
    assert rejected.status_code == 404
    groups = client.get("/api/media-groups?limit=100", headers=auth(owner_token)).json()
    assert "Must roll back" not in {group["name"] for group in groups["items"]}


def test_group_isolation_and_cross_scope_media_are_hidden(client):
    _, owner_token = new_user(client)
    _, stranger_token = new_user(client)
    owner_image = upload(client, owner_token).json()
    stranger_image = upload(client, stranger_token).json()
    group = _create_group(client, owner_token)

    assert client.get(
        f"/api/media-groups/{group['id']}", headers=auth(stranger_token)
    ).status_code == 404
    assert client.get(
        f"/api/media-groups/{group['id']}/items", headers=auth(stranger_token)
    ).status_code == 404

    cross_scope = client.post(
        f"/api/media-groups/{group['id']}/items",
        headers=auth(owner_token),
        json={"codes": [owner_image["code"], stranger_image["code"]]},
    )
    assert cross_scope.status_code == 404
    # Full-request validation means the allowed first code was not partially added.
    assert client.get(
        f"/api/media-groups/{group['id']}/items", headers=auth(owner_token)
    ).json()["total"] == 0

    mine = client.get("/api/media", headers=auth(owner_token)).json()
    assert {item["code"] for item in mine["items"]} == {owner_image["code"]}

    admin_token = login(client, "admin", "admin-pass")
    global_media = client.get("/api/media?limit=100", headers=auth(admin_token)).json()
    assert owner_image["code"] in {item["code"] for item in global_media["items"]}
    assert stranger_image["code"] in {item["code"] for item in global_media["items"]}
    assert client.get(
        f"/api/media-groups/{group['id']}", headers=auth(admin_token)
    ).status_code == 200


def test_team_groups_view_and_management_permissions(client):
    owner_name, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    _, outsider_token = new_user(client)
    team_id = _create_team(client, owner_token)
    add_member = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    )
    assert add_member.status_code == 201
    team_image = upload(client, member_token, data={"team_id": str(team_id)}).json()
    owner_group = _create_group(client, owner_token, team_id=team_id, name="Team picks")

    member_list = client.get(
        f"/api/media-groups?team_id={team_id}", headers=auth(member_token)
    )
    assert member_list.status_code == 200
    assert member_list.json()["items"][0]["owner_username"] == owner_name
    assert client.patch(
        f"/api/media-groups/{owner_group['id']}",
        headers=auth(member_token),
        json={"name": "not allowed"},
    ).status_code == 403
    assert client.get(
        f"/api/media-groups?team_id={team_id}", headers=auth(outsider_token)
    ).status_code == 404
    assert client.get(
        f"/api/media-groups/{owner_group['id']}", headers=auth(outsider_token)
    ).status_code == 404

    # A regular member may create and maintain their own shared group.
    member_group = _create_group(client, member_token, team_id=team_id, name="Member picks")
    add = client.post(
        f"/api/media-groups/{member_group['id']}/items",
        headers=auth(member_token),
        json={"codes": [team_image["code"]]},
    )
    assert add.status_code == 200
    assert add.json()["added"] == 1
    scoped = client.get(
        f"/api/media?team_id={team_id}&group_id={member_group['id']}",
        headers=auth(owner_token),
    ).json()
    assert scoped["total"] == 1
    assert scoped["items"][0]["team_id"] == team_id

    # Team owner is a manager and can update any shared group.
    assert client.patch(
        f"/api/media-groups/{member_group['id']}",
        headers=auth(owner_token),
        json={"name": "Curated by owner"},
    ).status_code == 200


def test_regular_member_can_leave_and_group_is_transferred(client):
    owner_name, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    _, outsider_token = new_user(client)
    team_id = _create_team(client, owner_token)
    membership = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    ).json()
    group = _create_group(client, member_token, team_id=team_id, name="Member handoff")

    # Another ordinary user cannot remove the member.
    assert client.delete(
        f"/api/teams/{team_id}/members/{membership['id']}", headers=auth(outsider_token)
    ).status_code == 403
    # The member may leave voluntarily; ownership transfers while still under
    # the same lifecycle lease.
    assert client.delete(
        f"/api/teams/{team_id}/members/{membership['id']}", headers=auth(member_token)
    ).status_code == 204
    assert client.get(
        f"/api/media-groups/{group['id']}", headers=auth(member_token)
    ).status_code == 404
    transferred = client.get(
        f"/api/media-groups/{group['id']}", headers=auth(owner_token)
    ).json()
    assert transferred["owner_username"] == owner_name


def test_asset_user_and_team_deletion_explicitly_clean_group_rows(client):
    admin_token = login(client, "admin", "admin-pass")
    owner_name, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    team_id = _create_team(client, owner_token)
    member_record = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    ).json()

    # Asset deletion removes its group membership but leaves the group.
    personal_image = upload(client, member_token).json()
    personal_group = _create_group(client, member_token, name="Temporary")
    client.post(
        f"/api/media-groups/{personal_group['id']}/items",
        headers=auth(member_token),
        json={"codes": [personal_image["code"]]},
    )
    assert client.delete(
        f"/api/images/{personal_image['code']}", headers=auth(member_token)
    ).status_code == 204
    assert client.get(
        f"/api/media-groups/{personal_group['id']}", headers=auth(member_token)
    ).json()["item_count"] == 0

    # Removing a member transfers their team groups to the team owner.
    shared_group = _create_group(client, member_token, team_id=team_id, name="Handoff")
    assert client.delete(
        f"/api/teams/{team_id}/members/{member_record['id']}", headers=auth(owner_token)
    ).status_code == 204
    handoff = client.get(
        f"/api/media-groups/{shared_group['id']}", headers=auth(owner_token)
    ).json()
    owner_id = client.get("/api/auth/me", headers=auth(owner_token)).json()["id"]
    assert handoff["owner_id"] == owner_id

    # Re-add the user, create another shared group, then delete the account.
    member_record = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    ).json()
    deleted_user_group = _create_group(client, member_token, team_id=team_id, name="User deletion")
    pending = init_video(client, member_token, MP4_HEADER + b"unfinished-video")
    assert pending.status_code == 201
    member_id = client.get("/api/auth/me", headers=auth(member_token)).json()["id"]
    assert client.delete(
        f"/api/admin/users/{member_id}", headers=auth(admin_token)
    ).status_code == 204
    transferred = client.get(
        f"/api/media-groups/{deleted_user_group['id']}", headers=auth(owner_token)
    ).json()
    assert transferred["owner_id"] == owner_id
    assert client.get(
        f"/api/media-groups/{personal_group['id']}", headers=auth(admin_token)
    ).status_code == 404

    # Dissolving the team deletes every shared group but returns team media to uploaders.
    assert client.delete(f"/api/teams/{team_id}", headers=auth(owner_token)).status_code == 204
    assert client.get(
        f"/api/media-groups/{shared_group['id']}", headers=auth(admin_token)
    ).status_code == 404
    assert client.get(
        f"/api/media-groups/{deleted_user_group['id']}", headers=auth(admin_token)
    ).status_code == 404


def test_library_stats_and_admin_user_creation(client):
    admin_token = login(client, "admin", "admin-pass")
    username = _uname("managed")
    created = client.post(
        "/api/admin/users",
        headers=auth(admin_token),
        json={"username": username, "password": "secure123", "role": "user"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["username"] == username
    assert login(client, username, "secure123")
    assert client.post(
        "/api/admin/users",
        headers=auth(admin_token),
        json={"username": username, "password": "secure123"},
    ).status_code == 409
    assert client.post(
        "/api/admin/users",
        headers=auth(admin_token),
        json={"username": _uname("badrole"), "password": "secure123", "role": "owner"},
    ).status_code == 422

    user_token = login(client, username, "secure123")
    assert client.post(
        "/api/admin/users",
        headers=auth(user_token),
        json={"username": _uname("forbidden"), "password": "secure123"},
    ).status_code == 403

    upload(client, user_token)
    _create_group(client, user_token, name="Overview group")
    personal = client.get("/api/library/stats", headers=auth(user_token)).json()
    assert personal["scope"] == "personal"
    assert personal["images"] == 1
    assert personal["media_total"] == 1
    assert personal["storage_bytes"] > 0
    assert personal["groups"] == 1

    global_stats = client.get("/api/library/stats", headers=auth(admin_token)).json()
    assert global_stats["scope"] == "global"
    assert global_stats["images"] >= personal["images"]
    assert global_stats["groups"] >= personal["groups"]


def test_delete_imageless_team_owner_does_not_leave_orphan_groups(client):
    admin_token = login(client, "admin", "admin-pass")
    victim_name, victim_token = new_user(client)
    survivor_name, survivor_token = new_user(client)

    survivor_team = _create_team(client, survivor_token)
    assert client.post(
        f"/api/teams/{survivor_team}/members",
        headers=auth(survivor_token),
        json={"username": victim_name},
    ).status_code == 201
    shared = _create_group(
        client, victim_token, team_id=survivor_team, name="Transfer without media"
    )
    personal = _create_group(client, victim_token, name="Empty personal")
    owned_team = _create_team(client, victim_token)
    owned_shared = _create_group(
        client, victim_token, team_id=owned_team, name="Dissolved owner group"
    )
    # Cancellation starts with rollback internally; deletion must still retain
    # the later group lifecycle operations.
    assert init_video(
        client, victim_token, MP4_HEADER + b"pending-without-final-media"
    ).status_code == 201

    victim_id = client.get("/api/auth/me", headers=auth(victim_token)).json()["id"]
    assert client.delete(
        f"/api/admin/users/{victim_id}", headers=auth(admin_token)
    ).status_code == 204

    assert client.get(
        f"/api/media-groups/{personal['id']}", headers=auth(admin_token)
    ).status_code == 404
    assert client.get(
        f"/api/media-groups/{owned_shared['id']}", headers=auth(admin_token)
    ).status_code == 404
    survivor_id = client.get("/api/auth/me", headers=auth(survivor_token)).json()["id"]
    transferred = client.get(
        f"/api/media-groups/{shared['id']}", headers=auth(survivor_token)
    ).json()
    assert transferred["owner_id"] == survivor_id
    assert transferred["owner_username"] == survivor_name


def test_library_lifecycle_lease_deterministically_blocks_mutation(client):
    _, token = new_user(client)
    image = upload(client, token).json()
    started = threading.Event()
    finished = threading.Event()
    result = {}

    def create_while_locked():
        started.set()
        response = client.post(
            "/api/media-groups",
            headers=auth(token),
            json={"name": f"locked-{_uname('g')}"},
        )
        result["status"] = response.status_code
        finished.set()

    with library_lifecycle_lease():
        worker = threading.Thread(target=create_while_locked)
        worker.start()
        assert started.wait(1)
        time.sleep(0.05)
        assert not finished.is_set()
    assert finished.wait(2)
    worker.join(timeout=2)
    assert result["status"] == 201

    delete_started = threading.Event()
    delete_finished = threading.Event()

    def delete_while_locked():
        delete_started.set()
        result["delete_status"] = client.delete(
            f"/api/images/{image['code']}", headers=auth(token)
        ).status_code
        delete_finished.set()

    with library_lifecycle_lease():
        delete_worker = threading.Thread(target=delete_while_locked)
        delete_worker.start()
        assert delete_started.wait(1)
        time.sleep(0.05)
        assert not delete_finished.is_set()
    assert delete_finished.wait(2)
    delete_worker.join(timeout=2)
    assert result["delete_status"] == 204
    assert client.get(f"/i/{image['code']}").status_code == 404


def test_orphan_cleanup_removes_missing_and_cross_scope_rows(client):
    _, first_token = new_user(client)
    _, second_token = new_user(client)
    first = upload(client, first_token).json()
    second = upload(client, second_token).json()
    first_group = _create_group(client, first_token, name="Valid")

    with SessionLocal() as db:
        first_media = db.execute(select(Image).where(Image.code == first["code"])).scalar_one()
        second_media = db.execute(select(Image).where(Image.code == second["code"])).scalar_one()
        db.add(
            MediaGroupItem(
                group_id=first_group["id"],
                media_id=first_media.id,
                added_by=first_media.owner_id,
            )
        )
        # Simulate manual/corrupt cross-owner metadata and missing references.
        db.add(
            MediaGroupItem(
                group_id=first_group["id"],
                media_id=second_media.id,
                added_by=999_999,
            )
        )
        db.add(
            MediaGroupItem(
                group_id=999_999,
                media_id=999_999,
                added_by=999_999,
            )
        )
        db.commit()

    assert cleanup_orphan_media_library() == 2
    assert cleanup_orphan_media_library() == 0
    items = client.get(
        f"/api/media-groups/{first_group['id']}/items", headers=auth(first_token)
    ).json()
    assert items["total"] == 1
    assert items["items"][0]["code"] == first["code"]


def test_waiting_group_add_revalidates_after_media_delete(client):
    _, token = new_user(client)
    media = upload(client, token).json()
    group = _create_group(client, token, name="Race-safe")
    started = threading.Event()
    finished = threading.Event()
    result = {}

    def add_after_waiting():
        started.set()
        response = client.post(
            f"/api/media-groups/{group['id']}/items",
            headers=auth(token),
            json={"codes": [media["code"]]},
        )
        result["status"] = response.status_code
        finished.set()

    with library_lifecycle_lease():
        worker = threading.Thread(target=add_after_waiting)
        worker.start()
        assert started.wait(1)
        time.sleep(0.05)
        assert not finished.is_set()
        with SessionLocal() as db:
            row = db.execute(select(Image).where(Image.code == media["code"])).scalar_one()
            # Re-entrant on this thread; queued add remains blocked until the
            # destructive lifecycle transaction and item cleanup commit.
            delete_image(db, row)

    assert finished.wait(2)
    worker.join(timeout=2)
    assert result["status"] == 404
    assert client.get(
        f"/api/media-groups/{group['id']}/items", headers=auth(token)
    ).json()["total"] == 0


def test_media_group_tables_have_no_foreign_keys_and_model_comments(client):
    # Trigger application startup/migration through the client fixture first.
    inspector = inspect(engine)
    assert inspector.get_foreign_keys("media_groups") == []
    assert inspector.get_foreign_keys("media_group_items") == []
    assert all(column.comment for column in MediaGroup.__table__.columns)
    assert all(column.comment for column in MediaGroupItem.__table__.columns)

    with SessionLocal() as db:
        # No stale membership rows should exist for already-deleted media.
        stale = db.execute(
            select(MediaGroupItem)
            .outerjoin(Image, Image.id == MediaGroupItem.media_id)
            .where(Image.id.is_(None))
        ).scalars().all()
        assert stale == []
