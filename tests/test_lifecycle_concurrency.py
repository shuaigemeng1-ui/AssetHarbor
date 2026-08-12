"""Deterministic races for owner/team-scoped row creation.

Every producer is paused exactly when it tries to enter the process-local
library lifecycle lease. A destructive operation then commits re-entrantly on
the controlling thread. Releasing the lease proves the waiting producer uses a
fresh snapshot and cannot commit stale owner/team authorization.
"""

import threading
from pathlib import Path

from sqlalchemy import func, select

from app.api.routes.admin import delete_user as delete_user_route
from app.api.routes.teams.members import remove_member as remove_member_route
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


def test_image_final_commit_rechecks_membership_after_request_body(monkeypatch, client):
    scope = _create_team_with_member(client)
    marker = f"blocked-image-{_uname('img')}"
    before_files = {
        path for path in Path("tests/_tmp_data/files").rglob("*") if path.is_file()
    }

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
    after_files = {
        path for path in Path("tests/_tmp_data/files").rglob("*") if path.is_file()
    }
    assert after_files == before_files


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
