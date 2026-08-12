"""Deterministic races for owner/team-scoped row creation.

Every producer is paused exactly when it tries to enter the process-local
library lifecycle lease. A destructive operation then commits re-entrantly on
the controlling thread. Releasing the lease proves the waiting producer uses a
fresh snapshot and cannot commit stale owner/team authorization.
"""

import threading

from sqlalchemy import func, select

from app.api.routes.admin import delete_user as delete_user_route
from app.api.routes.teams.members import remove_member as remove_member_route
from app.core.config import settings
from app.core.database import SessionLocal
from app.models import ApiKey, Image, Team, TeamMember, UploadSession, User
from app.services import library as library_service
from app.services.videos import dissolve_team_media
from conftest import (
    FAKE_PNG,
    MP4_HEADER,
    _uname,
    auth,
    init_video,
    login,
    new_user,
    put_video_part,
    upload,
    upload_video,
)


class _ObservedRLock:
    def __init__(self, delegate, reached: threading.Event):
        self.delegate = delegate
        self.reached = reached

    def __enter__(self):
        self.reached.set()
        self.delegate.acquire()
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        self.delegate.release()


def _run_waiting_request(monkeypatch, request_call, destructive_call):
    """Run request_call behind the lifecycle lease, then commit destruction."""
    original_lock = library_service._library_lifecycle_lock
    reached = threading.Event()
    finished = threading.Event()
    outcome = {}
    monkeypatch.setattr(
        library_service,
        "_library_lifecycle_lock",
        _ObservedRLock(original_lock, reached),
    )

    def worker():
        try:
            outcome["response"] = request_call()
        except BaseException as exc:  # surface worker errors in the test thread
            outcome["error"] = exc
        finally:
            finished.set()

    original_lock.acquire()
    try:
        thread = threading.Thread(target=worker)
        thread.start()
        assert reached.wait(2), "producer never reached its final lifecycle lease"
        assert not finished.is_set()
        destructive_call()
    finally:
        original_lock.release()

    assert finished.wait(5), "producer did not finish after lifecycle lease release"
    thread.join(timeout=2)
    if "error" in outcome:
        raise outcome["error"]
    return outcome["response"]


def _create_team_with_member(client):
    owner_name, owner_token = new_user(client)
    member_name, member_token = new_user(client)
    team = client.post(
        "/api/teams",
        headers=auth(owner_token),
        json={"name": f"race-team-{_uname('t')}"},
    )
    assert team.status_code == 201, team.text
    team_id = team.json()["id"]
    membership = client.post(
        f"/api/teams/{team_id}/members",
        headers=auth(owner_token),
        json={"username": member_name},
    )
    assert membership.status_code == 201, membership.text
    return {
        "owner_name": owner_name,
        "owner_token": owner_token,
        "member_name": member_name,
        "member_token": member_token,
        "member_id": membership.json()["id"],
        "team_id": team_id,
    }


def _remove_member_direct(scope):
    with SessionLocal() as db:
        owner = db.execute(
            select(User).where(User.username == scope["owner_name"])
        ).scalar_one()
        remove_member_route(
            scope["team_id"],
            scope["member_id"],
            current_user=owner,
            db=db,
        )


def _delete_user_direct(username: str):
    with SessionLocal() as db:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one()
        victim = db.execute(select(User).where(User.username == username)).scalar_one()
        delete_user_route(victim.id, current_user=admin, db=db)


def _initialize_team_video(client, scope):
    data = MP4_HEADER + b"lifecycle-race-video"
    initialized = init_video(
        client,
        scope["member_token"],
        data,
        filename="race.mp4",
        name="race-video",
        team_id=scope["team_id"],
    )
    assert initialized.status_code == 201, initialized.text
    upload_id = initialized.json()["upload_id"]
    part = put_video_part(
        client,
        scope["member_token"],
        upload_id,
        0,
        data,
        0,
        len(data),
    )
    assert part.status_code == 200, part.text
    return upload_id


def _promote_admin_actor(client):
    """Create a non-root administrator with a current post-promotion JWT."""
    root_token = login(client, "admin", "admin-pass")
    actor_name, _ = new_user(client)
    with SessionLocal() as db:
        actor_id = db.execute(
            select(User.id).where(User.username == actor_name)
        ).scalar_one()
    promoted = client.patch(
        f"/api/admin/users/{actor_id}/role",
        headers=auth(root_token),
        json={"role": "admin"},
    )
    assert promoted.status_code == 200, promoted.text
    return root_token, actor_name, actor_id, login(client, actor_name)


def _demote_actor(client, root_token, actor_id):
    demoted = client.patch(
        f"/api/admin/users/{actor_id}/role",
        headers=auth(root_token),
        json={"role": "user"},
    )
    assert demoted.status_code == 200, demoted.text


def test_image_final_commit_rechecks_membership_after_request_body(monkeypatch, client):
    scope = _create_team_with_member(client)
    marker = f"blocked-image-{_uname('img')}"
    before_files = {path for path in settings.files_dir.rglob("*") if path.is_file()}

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.post(
            "/api/upload",
            headers=auth(scope["member_token"]),
            data={"team_id": str(scope["team_id"]), "name": marker},
            files={"file": ("race.png", FAKE_PNG, "image/png")},
        ),
        lambda: _remove_member_direct(scope),
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.execute(select(Image).where(Image.name == marker)).scalar_one_or_none() is None
    after_files = {path for path in settings.files_dir.rglob("*") if path.is_file()}
    assert after_files == before_files


def _promote_scope_member(client, scope):
    promoted = client.patch(
        f"/api/teams/{scope['team_id']}/members/{scope['member_id']}",
        headers=auth(scope["owner_token"]),
        json={"role": "admin"},
    )
    assert promoted.status_code == 200, promoted.text


def test_image_patch_rechecks_team_manager_after_removal(monkeypatch, client):
    scope = _create_team_with_member(client)
    _promote_scope_member(client, scope)
    created = upload(
        client,
        scope["owner_token"],
        data={"team_id": str(scope["team_id"]), "name": "before-image-patch"},
    )
    assert created.status_code == 201, created.text
    code = created.json()["code"]

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.patch(
            f"/api/images/{code}",
            headers=auth(scope["member_token"]),
            json={"name": "stale-image-patch", "visibility": "private"},
        ),
        lambda: _remove_member_direct(scope),
    )

    assert response.status_code == 403
    with SessionLocal() as db:
        image = db.execute(select(Image).where(Image.code == code)).scalar_one()
        assert image.name == "before-image-patch"
        assert image.visibility == "public"


def test_video_patch_rechecks_team_manager_after_removal(monkeypatch, client):
    scope = _create_team_with_member(client)
    _promote_scope_member(client, scope)
    _, video = upload_video(
        client,
        scope["owner_token"],
        team_id=scope["team_id"],
        name="before-video-patch",
    )
    code = video["code"]

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.patch(
            f"/api/videos/{code}",
            headers=auth(scope["member_token"]),
            json={"name": "stale-video-patch", "visibility": "private"},
        ),
        lambda: _remove_member_direct(scope),
    )

    assert response.status_code == 403
    with SessionLocal() as db:
        video_row = db.execute(select(Image).where(Image.code == code)).scalar_one()
        assert video_row.name == "before-video-patch"
        assert video_row.visibility == "public"


def test_video_init_cannot_commit_after_admin_deletes_owner(monkeypatch, client):
    username, token = new_user(client)
    data = MP4_HEADER + b"blocked-init"
    with SessionLocal() as db:
        owner_id = db.execute(select(User.id).where(User.username == username)).scalar_one()

    response = _run_waiting_request(
        monkeypatch,
        lambda: init_video(client, token, data, filename="deleted-owner.mp4"),
        lambda: _delete_user_direct(username),
    )

    assert response.status_code == 401
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count()).select_from(UploadSession).where(UploadSession.owner_id == owner_id)
        ) == 0


def test_admin_cancel_waiting_on_put_rechecks_demotion(client):
    """A stale administrator cannot delete another owner's resumable work."""
    from app.services import videos

    root_token, _actor_name, actor_id, actor_token = _promote_admin_actor(client)
    _, owner_token = new_user(client)
    data = MP4_HEADER + b"cancel-demotion-race"
    created = init_video(client, owner_token, data)
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload_id"]

    gate = videos._lease_inbound_upload_gate(upload_id)
    gate.acquire()
    finished = threading.Event()
    outcome = {}

    def cancel_worker():
        try:
            outcome["response"] = client.delete(
                f"/api/video-uploads/{upload_id}", headers=auth(actor_token)
            )
        finally:
            finished.set()

    thread = threading.Thread(target=cancel_worker)
    thread.start()
    try:
        # The DELETE passed its route-level admin check and is now queued on
        # the same gate as an inbound PUT.
        for _ in range(400):
            with videos._inbound_gate_guard:
                if videos._inbound_gate_users.get(upload_id) == 2:
                    break
            threading.Event().wait(0.005)
        with videos._inbound_gate_guard:
            assert videos._inbound_gate_users.get(upload_id) == 2
        _demote_actor(client, root_token, actor_id)
    finally:
        gate.release()
        videos._release_inbound_upload_gate(upload_id, gate)

    assert finished.wait(5)
    thread.join(timeout=2)
    assert outcome["response"].status_code == 404
    status_response = client.get(
        f"/api/video-uploads/{upload_id}", headers=auth(owner_token)
    )
    assert status_response.status_code == 200, status_response.text
    assert put_video_part(
        client, owner_token, upload_id, 0, data, 0, len(data)
    ).status_code == 200


def test_unchanged_admin_can_cancel_another_users_upload(client):
    root_token = login(client, "admin", "admin-pass")
    _, owner_token = new_user(client)
    data = MP4_HEADER + b"admin-cancel"
    upload_id = init_video(client, owner_token, data).json()["upload_id"]
    canceled = client.delete(
        f"/api/video-uploads/{upload_id}", headers=auth(root_token)
    )
    assert canceled.status_code == 204, canceled.text
    assert client.get(
        f"/api/video-uploads/{upload_id}", headers=auth(owner_token)
    ).status_code == 404


def test_admin_put_rechecks_demotion_after_body_stream(monkeypatch, client):
    """Final part registration cannot rely on pre-stream administrator role."""
    from app.services import videos

    root_token, _actor_name, actor_id, actor_token = _promote_admin_actor(client)
    _, owner_token = new_user(client)
    data = MP4_HEADER + b"put-demotion-race"
    upload_id = init_video(client, owner_token, data).json()["upload_id"]
    real_commit = videos._commit_upload_part
    reached_commit = threading.Event()
    release_commit = threading.Event()
    finished = threading.Event()
    outcome = {}

    def blocked_commit(*args, **kwargs):
        reached_commit.set()
        assert release_commit.wait(5), "test did not release staged PUT"
        return real_commit(*args, **kwargs)

    monkeypatch.setattr(videos, "_commit_upload_part", blocked_commit)

    def put_worker():
        try:
            outcome["response"] = put_video_part(
                client, actor_token, upload_id, 0, data, 0, len(data)
            )
        finally:
            finished.set()

    thread = threading.Thread(target=put_worker)
    thread.start()
    assert reached_commit.wait(2), "PUT never reached post-stream commit"
    try:
        _demote_actor(client, root_token, actor_id)
    finally:
        release_commit.set()

    assert finished.wait(5)
    thread.join(timeout=2)
    assert outcome["response"].status_code == 404
    with SessionLocal() as db:
        assert db.scalar(
            select(func.count())
            .select_from(UploadSession)
            .where(UploadSession.upload_id == upload_id)
        ) == 1
        from app.models import UploadPart

        assert db.scalar(
            select(func.count())
            .select_from(UploadPart)
            .where(UploadPart.upload_id == upload_id)
        ) == 0
    # The owner can still publish the same part after stale-admin rejection.
    assert put_video_part(
        client, owner_token, upload_id, 0, data, 0, len(data)
    ).status_code == 200


def test_removed_member_idempotent_put_does_not_extend_session(client):
    scope = _create_team_with_member(client)
    data = MP4_HEADER + b"member-repeat-after-removal"
    created = init_video(
        client,
        scope["member_token"],
        data,
        team_id=scope["team_id"],
    )
    assert created.status_code == 201, created.text
    upload_id = created.json()["upload_id"]
    assert put_video_part(
        client, scope["member_token"], upload_id, 0, data, 0, len(data)
    ).status_code == 200
    with SessionLocal() as db:
        before = db.get(UploadSession, upload_id).expires_at

    _remove_member_direct(scope)
    repeated = put_video_part(
        client, scope["member_token"], upload_id, 0, data, 0, len(data)
    )
    assert repeated.status_code == 403
    with SessionLocal() as db:
        after = db.get(UploadSession, upload_id).expires_at
        assert after == before


def test_video_complete_cannot_commit_after_member_is_removed(monkeypatch, client):
    scope = _create_team_with_member(client)
    upload_id = _initialize_team_video(client, scope)

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.post(
            f"/api/video-uploads/{upload_id}/complete",
            headers=auth(scope["member_token"]),
        ),
        lambda: _remove_member_direct(scope),
    )

    assert response.status_code == 403
    with SessionLocal() as db:
        upload = db.get(UploadSession, upload_id)
        assert upload is not None and upload.status == "active"
        assert db.execute(
            select(Image).where(Image.owner_id == upload.owner_id, Image.media_kind == "video")
        ).scalar_one_or_none() is None


def test_video_hash_releases_library_lock_and_final_auth_blocks_revoked_member(
    monkeypatch, client
):
    from app.services import videos

    scope = _create_team_with_member(client)
    upload_id = _initialize_team_video(client, scope)
    real_verify = videos._verify_parts_and_sha256
    hashing = threading.Event()
    release_hash = threading.Event()
    completed = threading.Event()
    outcome = {}

    def blocked_verify(path, parts):
        hashing.set()
        assert release_hash.wait(5), "test did not release video hashing"
        return real_verify(path, parts)

    monkeypatch.setattr(videos, "_verify_parts_and_sha256", blocked_verify)

    def complete_worker():
        try:
            outcome["response"] = client.post(
                f"/api/video-uploads/{upload_id}/complete",
                headers=auth(scope["member_token"]),
            )
        finally:
            completed.set()

    complete_thread = threading.Thread(target=complete_worker)
    complete_thread.start()
    assert hashing.wait(2), "completion never entered the unlocked hash phase"

    listing_done = threading.Event()
    listing = {}

    def list_worker():
        listing["response"] = client.get(
            "/api/media", headers=auth(scope["member_token"])
        )
        listing_done.set()

    list_thread = threading.Thread(target=list_worker)
    list_thread.start()
    try:
        assert listing_done.wait(2), "media GET was blocked by whole-file hashing"
        assert listing["response"].status_code == 200
        _remove_member_direct(scope)
    finally:
        release_hash.set()

    assert completed.wait(5)
    complete_thread.join(timeout=2)
    list_thread.join(timeout=2)
    assert outcome["response"].status_code == 403
    with SessionLocal() as db:
        upload_row = db.get(UploadSession, upload_id)
        assert upload_row is not None and upload_row.status == "active"
        assert db.execute(
            select(Image).where(
                Image.owner_id == upload_row.owner_id,
                Image.media_kind == "video",
            )
        ).scalar_one_or_none() is None


def test_cancel_during_unlocked_video_hash_prevents_publication(monkeypatch, client):
    from app.services import videos

    username, token = new_user(client)
    data = MP4_HEADER + b"cancel-during-hash"
    initialized = init_video(client, token, data)
    upload_id = initialized.json()["upload_id"]
    assert put_video_part(client, token, upload_id, 0, data, 0, len(data)).status_code == 200
    with SessionLocal() as db:
        owner_id = db.execute(
            select(User.id).where(User.username == username)
        ).scalar_one()

    real_verify = videos._verify_parts_and_sha256
    hashing = threading.Event()
    release_hash = threading.Event()
    outcome = {}

    def blocked_verify(path, parts):
        hashing.set()
        assert release_hash.wait(5)
        return real_verify(path, parts)

    monkeypatch.setattr(videos, "_verify_parts_and_sha256", blocked_verify)

    def worker():
        outcome["response"] = client.post(
            f"/api/video-uploads/{upload_id}/complete", headers=auth(token)
        )

    thread = threading.Thread(target=worker)
    thread.start()
    assert hashing.wait(2)
    try:
        canceled = client.delete(
            f"/api/video-uploads/{upload_id}", headers=auth(token)
        )
        assert canceled.status_code == 204
    finally:
        release_hash.set()
    thread.join(timeout=5)

    assert outcome["response"].status_code == 404
    with SessionLocal() as db:
        assert db.get(UploadSession, upload_id) is None
        assert db.execute(
            select(Image).where(
                Image.owner_id == owner_id,
                Image.media_kind == "video",
            )
        ).scalar_one_or_none() is None


def test_deleted_admin_actor_during_video_hash_restores_owner_session(
    monkeypatch, client
):
    """Deleting a delegated admin must not strand another user's upload."""
    from app.services import videos

    root_token = login(client, "admin", "admin-pass")
    actor_name, _ = new_user(client)
    with SessionLocal() as db:
        actor_id = db.execute(
            select(User.id).where(User.username == actor_name)
        ).scalar_one()
    promoted = client.patch(
        f"/api/admin/users/{actor_id}/role",
        headers=auth(root_token),
        json={"role": "admin"},
    )
    assert promoted.status_code == 200, promoted.text
    actor_token = login(client, actor_name)

    owner_name, owner_token = new_user(client)
    data = MP4_HEADER + b"deleted-admin-during-hash"
    initialized = init_video(client, owner_token, data)
    assert initialized.status_code == 201, initialized.text
    upload_id = initialized.json()["upload_id"]
    assert put_video_part(
        client, owner_token, upload_id, 0, data, 0, len(data)
    ).status_code == 200

    real_verify = videos._verify_parts_and_sha256
    hashing = threading.Event()
    release_hash = threading.Event()
    finished = threading.Event()
    outcome = {}

    def blocked_verify(path, parts):
        hashing.set()
        assert release_hash.wait(5), "test did not release video hashing"
        return real_verify(path, parts)

    monkeypatch.setattr(videos, "_verify_parts_and_sha256", blocked_verify)

    def complete_worker():
        try:
            outcome["response"] = client.post(
                f"/api/video-uploads/{upload_id}/complete",
                headers=auth(actor_token),
            )
        finally:
            finished.set()

    thread = threading.Thread(target=complete_worker)
    thread.start()
    assert hashing.wait(2), "completion never entered the unlocked hash phase"
    try:
        deleted = client.delete(
            f"/api/admin/users/{actor_id}", headers=auth(root_token)
        )
        assert deleted.status_code == 204, deleted.text
    finally:
        release_hash.set()

    assert finished.wait(5), "completion did not finish after actor deletion"
    thread.join(timeout=2)
    assert outcome["response"].status_code == 401
    owner_status = client.get(
        f"/api/video-uploads/{upload_id}", headers=auth(owner_token)
    )
    assert owner_status.status_code == 200, owner_status.text
    assert owner_status.json()["status"] in {"active", "failed"}

    with SessionLocal() as db:
        owner_id = db.execute(
            select(User.id).where(User.username == owner_name)
        ).scalar_one()
        upload_row = db.get(UploadSession, upload_id)
        assert upload_row is not None
        assert upload_row.status in {"active", "failed"}
        assert db.execute(
            select(Image).where(
                Image.owner_id == owner_id,
                Image.media_kind == "video",
            )
        ).scalar_one_or_none() is None


def test_team_dissolve_wins_before_video_complete_without_orphan(monkeypatch, client):
    scope = _create_team_with_member(client)
    upload_id = _initialize_team_video(client, scope)

    def dissolve_direct():
        with SessionLocal() as db:
            team = db.get(Team, scope["team_id"])
            assert team is not None
            dissolve_team_media(db, team)

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.post(
            f"/api/video-uploads/{upload_id}/complete",
            headers=auth(scope["member_token"]),
        ),
        dissolve_direct,
    )

    assert response.status_code == 200, response.text
    assert response.json()["team_id"] is None
    with SessionLocal() as db:
        assert db.get(Team, scope["team_id"]) is None
        video = db.execute(
            select(Image).where(Image.code == response.json()["code"])
        ).scalar_one()
        assert video.owner_id is not None and video.team_id is None


def test_team_creation_cannot_commit_after_owner_deletion(monkeypatch, client):
    username, token = new_user(client)
    with SessionLocal() as db:
        owner_id = db.execute(select(User.id).where(User.username == username)).scalar_one()
    team_name = f"blocked-team-{_uname('t')}"

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.post("/api/teams", headers=auth(token), json={"name": team_name}),
        lambda: _delete_user_direct(username),
    )

    assert response.status_code == 401
    with SessionLocal() as db:
        assert db.execute(select(Team).where(Team.name == team_name)).scalar_one_or_none() is None
        assert db.execute(
            select(TeamMember).where(TeamMember.user_id == owner_id)
        ).scalar_one_or_none() is None


def test_api_key_creation_cannot_commit_after_owner_deletion(monkeypatch, client):
    username, token = new_user(client)
    with SessionLocal() as db:
        owner_id = db.execute(select(User.id).where(User.username == username)).scalar_one()

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.post(
            "/api/keys", headers=auth(token), json={"name": "blocked-key"}
        ),
        lambda: _delete_user_direct(username),
    )

    assert response.status_code == 401
    with SessionLocal() as db:
        assert db.execute(
            select(ApiKey).where(ApiKey.user_id == owner_id)
        ).scalar_one_or_none() is None


def test_admin_user_creation_rechecks_role_after_password_hash(monkeypatch, client):
    from app.api.routes import admin as admin_routes

    root_token, _actor_name, actor_id, actor_token = _promote_admin_actor(client)
    target_name = _uname("blocked-created-user")
    real_hash = admin_routes.hash_password
    hashing = threading.Event()
    release_hash = threading.Event()
    finished = threading.Event()
    outcome = {}

    def blocked_hash(password):
        hashing.set()
        assert release_hash.wait(5), "test did not release password hashing"
        return real_hash(password)

    monkeypatch.setattr(admin_routes, "hash_password", blocked_hash)

    def create_worker():
        try:
            outcome["response"] = client.post(
                "/api/admin/users",
                headers=auth(actor_token),
                json={
                    "username": target_name,
                    "password": "password123",
                    "role": "user",
                },
            )
        finally:
            finished.set()

    thread = threading.Thread(target=create_worker)
    thread.start()
    assert hashing.wait(2), "user creation never entered password hashing"
    try:
        _demote_actor(client, root_token, actor_id)
    finally:
        release_hash.set()

    assert finished.wait(5)
    thread.join(timeout=2)
    assert outcome["response"].status_code == 403
    with SessionLocal() as db:
        assert db.execute(
            select(User).where(User.username == target_name)
        ).scalar_one_or_none() is None


def test_member_role_change_reloads_after_member_removal(monkeypatch, client):
    scope = _create_team_with_member(client)

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.patch(
            f"/api/teams/{scope['team_id']}/members/{scope['member_id']}",
            headers=auth(scope["owner_token"]),
            json={"role": "admin"},
        ),
        lambda: _remove_member_direct(scope),
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        assert db.get(TeamMember, scope["member_id"]) is None


def test_add_member_reloads_target_after_admin_deletion(monkeypatch, client):
    owner_name, owner_token = new_user(client)
    target_name, _target_token = new_user(client)
    team = client.post(
        "/api/teams",
        headers=auth(owner_token),
        json={"name": f"add-race-{_uname('t')}"},
    )
    assert team.status_code == 201
    team_id = team.json()["id"]

    response = _run_waiting_request(
        monkeypatch,
        lambda: client.post(
            f"/api/teams/{team_id}/members",
            headers=auth(owner_token),
            json={"username": target_name},
        ),
        lambda: _delete_user_direct(target_name),
    )

    assert response.status_code == 404
    with SessionLocal() as db:
        owner_id = db.execute(select(User.id).where(User.username == owner_name)).scalar_one()
        team_row = db.get(Team, team_id)
        assert team_row is not None and team_row.owner_id == owner_id
        assert db.scalar(
            select(func.count()).select_from(TeamMember).where(TeamMember.team_id == team_id)
        ) == 1
