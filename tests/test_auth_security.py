"""Focused authentication hardening and bootstrap migration tests."""

from datetime import datetime, timedelta, timezone
import threading

import bcrypt
import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import app.api.routes.admin as admin_routes
import app.api.routes.auth as auth_routes
from app.core import database, security
from app.core.config import settings
from app.models import RuntimeCounter, User
from app.schemas import ResetPasswordRequest
from app.services.identifiers import next_user_id
from conftest import _uname, auth, login, new_user


def _isolated_user_sessions(tmp_path, filename="users.db"):
    isolated_engine = create_engine(f"sqlite:///{tmp_path / filename}")
    User.__table__.create(bind=isolated_engine)
    RuntimeCounter.__table__.create(bind=isolated_engine)
    return isolated_engine, sessionmaker(
        bind=isolated_engine,
        autoflush=False,
        expire_on_commit=False,
    )


def test_password_hash_uses_prefixed_bcrypt_sha256_and_accepts_legacy_bcrypt():
    password = "correct horse battery staple"
    current_hash = security.hash_password(password)
    assert current_hash.startswith("bcrypt-sha256:")
    assert security.verify_password(password, current_hash)
    assert not security.verify_password(password + "!", current_hash)

    # Pre-hashing must distinguish secrets that bcrypt itself would truncate
    # to the same first 72 bytes.
    long_hash = security.hash_password("a" * 72 + "x")
    assert security.verify_password("a" * 72 + "x", long_hash)
    assert not security.verify_password("a" * 72 + "y", long_hash)

    legacy_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("ascii")
    assert security.verify_password(password, legacy_hash)
    assert not security.verify_password(password + "!", legacy_hash)


def test_successful_login_upgrades_legacy_bcrypt_hash(client):
    username = _uname("legacy_hash")
    password = "legacy-password"
    legacy_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("ascii")
    with database.SessionLocal() as db:
        db.add(User(username=username, password_hash=legacy_hash, role="user"))
        db.commit()

    response = client.post(
        "/api/auth/login",
        data={"username": username, "password": password},
    )
    assert response.status_code == 200
    with database.SessionLocal() as db:
        stored = db.query(User).filter_by(username=username).one()
        assert stored.password_hash.startswith("bcrypt-sha256:")
        assert security.verify_password(password, stored.password_hash)


def test_legacy_hash_upgrade_cannot_overwrite_concurrent_admin_reset(client, monkeypatch):
    username = _uname("legacy_race")
    password = "legacy-password"
    reset_password = "administrator-reset"
    legacy_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode("ascii")
    with database.SessionLocal() as db:
        user = User(username=username, password_hash=legacy_hash, role="user")
        db.add(user)
        db.commit()
        user_id = user.id

    admin_token = login(client, "admin", "admin-pass")
    real_hash_password = auth_routes.hash_password
    upgrade_started = threading.Event()
    release_upgrade = threading.Event()

    def blocked_upgrade(value: str) -> str:
        if value == password:
            upgrade_started.set()
            assert release_upgrade.wait(5)
        return real_hash_password(value)

    monkeypatch.setattr(auth_routes, "hash_password", blocked_upgrade)
    result = {}

    def login_worker():
        result["response"] = client.post(
            "/api/auth/login",
            data={"username": username, "password": password},
        )

    thread = threading.Thread(target=login_worker)
    thread.start()
    assert upgrade_started.wait(2)
    try:
        reset = client.patch(
            f"/api/admin/users/{user_id}/password",
            headers=auth(admin_token),
            json={"new_password": reset_password},
        )
        assert reset.status_code == 204, reset.text
    finally:
        release_upgrade.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert result["response"].status_code == 401
    assert client.post(
        "/api/auth/login", data={"username": username, "password": password}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", data={"username": username, "password": reset_password}
    ).status_code == 200


def test_change_password_cas_loses_safely_to_concurrent_admin_reset(client, monkeypatch):
    username, token = new_user(client)
    with database.SessionLocal() as db:
        user_id = db.query(User).filter_by(username=username).one().id
    admin_token = login(client, "admin", "admin-pass")
    requested_password = "self-requested-password"
    reset_password = "administrator-wins"
    real_hash_password = auth_routes.hash_password
    change_started = threading.Event()
    release_change = threading.Event()

    def blocked_change(value: str) -> str:
        if value == requested_password:
            change_started.set()
            assert release_change.wait(5)
        return real_hash_password(value)

    monkeypatch.setattr(auth_routes, "hash_password", blocked_change)
    result = {}

    def change_worker():
        result["response"] = client.post(
            "/api/auth/change-password",
            headers=auth(token),
            json={"old_password": "pass123", "new_password": requested_password},
        )

    thread = threading.Thread(target=change_worker)
    thread.start()
    assert change_started.wait(2)
    try:
        reset = client.patch(
            f"/api/admin/users/{user_id}/password",
            headers=auth(admin_token),
            json={"new_password": reset_password},
        )
        assert reset.status_code == 204, reset.text
    finally:
        release_change.set()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert result["response"].status_code == 409
    assert client.post(
        "/api/auth/login", data={"username": username, "password": "pass123"}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", data={"username": username, "password": requested_password}
    ).status_code == 401
    assert client.post(
        "/api/auth/login", data={"username": username, "password": reset_password}
    ).status_code == 200


def test_sql_expression_revocation_does_not_lose_stale_session_increment(client):
    username, _ = new_user(client)
    with database.SessionLocal() as first, database.SessionLocal() as second:
        first_user = first.query(User).filter_by(username=username).one()
        second_user = second.query(User).filter_by(username=username).one()
        original_version = first_user.auth_version

        security.revoke_user_jwts(first_user)
        first.commit()
        security.revoke_user_jwts(second_user)
        second.commit()

    with database.SessionLocal() as db:
        stored = db.query(User).filter_by(username=username).one()
        assert stored.auth_version == original_version + 2


def test_admin_reset_rechecks_stale_actor_role_inside_lifecycle_lease(client):
    with database.SessionLocal() as stale_session:
        actor = User(
            username=_uname("reset_actor"),
            password_hash=security.hash_password("actor-password"),
            role="admin",
        )
        target = User(
            username=_uname("reset_target"),
            password_hash=security.hash_password("target-password"),
            role="user",
        )
        stale_session.add_all((actor, target))
        stale_session.commit()
        actor_id = actor.id
        target_id = target.id
        original_target_hash = target.password_hash

        with database.SessionLocal() as winning_session:
            winning_actor = winning_session.get(User, actor_id)
            winning_actor.role = "user"
            security.revoke_user_jwts(winning_actor)
            winning_session.commit()

        with pytest.raises(HTTPException) as rejected:
            admin_routes.reset_password(
                target_id,
                ResetPasswordRequest(new_password="must-not-win"),
                current_user=actor,
                db=stale_session,
            )
        assert rejected.value.status_code == 403

    with database.SessionLocal() as db:
        assert db.get(User, target_id).password_hash == original_target_hash


def test_pre_migration_jwt_without_generation_claims_is_rejected(client):
    username, current_token = new_user(client)
    with database.SessionLocal() as db:
        user = db.query(User).filter_by(username=username).one()
        now = datetime.now(timezone.utc)
        legacy_token = jwt.encode(
            {
                "sub": str(user.id),
                "username": user.username,
                "role": user.role,
                "iat": now,
                "exp": now + timedelta(minutes=10),
            },
            security._JWT_SECRET,
            algorithm=security._ALGORITHM,
        )

    assert client.get("/api/auth/me", headers=auth(legacy_token)).status_code == 401


def test_deleted_user_jwt_cannot_authenticate_reused_account_id(client):
    username, old_token = new_user(client)
    old_user = client.get("/api/auth/me", headers=auth(old_token)).json()
    admin_token = login(client, "admin", "admin-pass")
    assert client.delete(
        f"/api/admin/users/{old_user['id']}", headers=auth(admin_token)
    ).status_code == 204

    replacement = client.post(
        "/api/admin/users",
        headers=auth(admin_token),
        json={"username": f"replacement-{old_user['id']}", "password": "pass123", "role": "user"},
    )
    assert replacement.status_code == 201
    assert replacement.json()["id"] > old_user["id"]
    assert client.get("/api/auth/me", headers=auth(old_token)).status_code == 401


def test_fresh_library_user_rejects_reused_account_identity(client):
    from app.core.auth_scope import bind_auth_scope
    from app.services.library import fresh_library_user

    username, _token = new_user(client)
    with database.SessionLocal() as stale_db:
        stale_actor = stale_db.query(User).filter_by(username=username).one()
        bind_auth_scope(stale_actor, "jwt")
        stale_id = stale_actor.id

        admin_token = login(client, "admin", "admin-pass")
        assert client.delete(
            f"/api/admin/users/{stale_id}", headers=auth(admin_token)
        ).status_code == 204
        replacement = client.post(
            "/api/admin/users",
            headers=auth(admin_token),
            json={"username": f"fresh-replacement-{stale_id}", "password": "pass123", "role": "user"},
        )
        assert replacement.status_code == 201
        assert replacement.json()["id"] > stale_id

        stale_db.rollback()
        with pytest.raises(HTTPException) as rejected:
            fresh_library_user(stale_db, stale_actor)
        assert rejected.value.status_code == 401


def test_login_for_missing_account_runs_fixed_dummy_bcrypt(client, monkeypatch):
    calls: list[str] = []

    def record_verification(_password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return False

    monkeypatch.setattr(security, "verify_password", record_verification)
    response = client.post(
        "/api/auth/login",
        data={"username": _uname("missing"), "password": "not-the-password"},
    )
    assert response.status_code == 401
    assert calls == [security._DUMMY_PASSWORD_HASH]


def test_password_change_revokes_jwt_but_keeps_api_key(client):
    _, old_token = new_user(client)
    key_response = client.post("/api/keys", headers=auth(old_token))
    assert key_response.status_code == 201
    api_key = key_response.json()["key"]

    changed = client.post(
        "/api/auth/change-password",
        headers=auth(old_token),
        json={"old_password": "pass123", "new_password": "newpass1"},
    )
    assert changed.status_code == 204
    assert client.get("/api/auth/me", headers=auth(old_token)).status_code == 401
    assert client.get("/api/auth/me", headers={"X-API-Key": api_key}).status_code == 200


def test_auth_version_migration_is_idempotent_and_has_no_foreign_key(tmp_path, monkeypatch):
    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy-auth.db'}")
    with legacy_engine.begin() as conn:
        conn.execute(text("CREATE TABLE images (id INTEGER PRIMARY KEY, code VARCHAR(32))"))
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR(64) NOT NULL,
                    password_hash VARCHAR(128) NOT NULL,
                    role VARCHAR(16) NOT NULL,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )
        conn.execute(text("CREATE TABLE teams (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE team_members (id INTEGER PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE api_keys (id INTEGER PRIMARY KEY)"))
        conn.execute(text("INSERT INTO teams (id) VALUES (10)"))
        conn.execute(text("INSERT INTO team_members (id) VALUES (20)"))
        conn.execute(text("INSERT INTO api_keys (id) VALUES (30)"))
        conn.execute(
            text(
                """
                INSERT INTO users (id, username, password_hash, role, created_at)
                VALUES (1, 'legacy', 'legacy-hash', 'user', '2026-01-01 00:00:00')
                """
            )
        )

    monkeypatch.setattr(database, "engine", legacy_engine)
    database._migrate()
    database._migrate()

    with legacy_engine.connect() as conn:
        columns = {row[1]: row for row in conn.execute(text("PRAGMA table_info(users)"))}
        assert columns["auth_version"][2].upper() == "INTEGER"
        assert columns["auth_version"][3] == 1
        assert str(columns["auth_version"][4]).strip("'\"") == "1"
        assert conn.execute(text("SELECT auth_version FROM users WHERE id = 1")).scalar_one() == 1
        assert conn.execute(text("PRAGMA foreign_key_list(users)")).all() == []
        assert conn.execute(
            text("SELECT value FROM runtime_counters WHERE name = 'user_id'")
        ).scalar_one() == 1
        assert conn.execute(text("PRAGMA foreign_key_list(runtime_counters)")).all() == []
        assert conn.execute(
            text("SELECT value FROM runtime_counters WHERE name = 'team_id'")
        ).scalar_one() == 10
        assert conn.execute(
            text("SELECT value FROM runtime_counters WHERE name = 'team_member_id'")
        ).scalar_one() == 20
        assert conn.execute(
            text("SELECT value FROM runtime_counters WHERE name = 'media_group_id'")
        ).scalar_one() == 0
        assert conn.execute(
            text("SELECT value FROM runtime_counters WHERE name = 'api_key_id'")
        ).scalar_one() == 30

    legacy_sessions = sessionmaker(
        bind=legacy_engine, autoflush=False, expire_on_commit=False
    )
    with legacy_sessions() as db:
        db.execute(text("DELETE FROM users WHERE id = 1"))
        db.commit()
        replacement = User(
            id=next_user_id(db),
            username="replacement",
            password_hash="replacement-hash",
            role="user",
        )
        db.add(replacement)
        db.commit()
        assert replacement.id == 2

        # Even when the legacy highest rows are deleted before the first new
        # allocation, migration-seeded high-water marks prevent stale URL ABA.
        db.execute(text("DELETE FROM teams WHERE id = 10"))
        db.execute(text("DELETE FROM team_members WHERE id = 20"))
        db.execute(text("DELETE FROM api_keys WHERE id = 30"))
        db.commit()
        from app.api.routes.keys import _next_api_key_id
        from app.services.identifiers import (
            next_media_group_id,
            next_team_id,
            next_team_member_id,
        )

        assert next_team_id(db) == 11
        assert next_team_member_id(db) == 21
        assert next_media_group_id(db) == 1
        assert _next_api_key_id(db) == 31


def test_ensure_admin_only_revokes_when_password_or_role_actually_changes(tmp_path, monkeypatch):
    _, isolated_sessions = _isolated_user_sessions(tmp_path, "ensure-admin.db")
    monkeypatch.setattr(security, "SessionLocal", isolated_sessions)
    monkeypatch.setattr(settings, "admin_password", "same-admin-password")

    security.ensure_admin()
    with isolated_sessions() as db:
        admin = db.execute(text("SELECT password_hash, role, auth_version FROM users")).one()
    original_hash, _, original_version = admin

    security.ensure_admin()
    with isolated_sessions() as db:
        unchanged = db.execute(text("SELECT password_hash, role, auth_version FROM users")).one()
    assert tuple(unchanged) == (original_hash, "admin", original_version)

    with isolated_sessions() as db:
        stored = db.query(User).filter_by(username="admin").one()
        stored.role = "user"
        db.commit()
    security.ensure_admin()
    with isolated_sessions() as db:
        corrected = db.execute(text("SELECT password_hash, role, auth_version FROM users")).one()
    assert tuple(corrected) == (original_hash, "admin", original_version + 1)

    monkeypatch.setattr(settings, "admin_password", "different-admin-password")
    security.ensure_admin()
    with isolated_sessions() as db:
        changed = db.query(User).filter_by(username="admin").one()
        assert changed.auth_version == original_version + 2
        assert security.verify_password("different-admin-password", changed.password_hash)


def test_closed_empty_installation_fails_fast_but_existing_user_is_allowed(tmp_path, monkeypatch):
    _, isolated_sessions = _isolated_user_sessions(tmp_path, "bootstrap.db")
    monkeypatch.setattr(settings, "allow_registration", "closed")
    monkeypatch.setattr(settings, "admin_password", "")

    with pytest.raises(RuntimeError, match="OSS_ADMIN_PASSWORD"):
        security.validate_bootstrap_state(session_factory=isolated_sessions)

    with isolated_sessions() as db:
        db.add(
            User(
                username="existing-user",
                password_hash=security.hash_password("existing-password"),
                role="user",
                created_at=datetime(2026, 1, 1),
            )
        )
        db.commit()

    security.validate_bootstrap_state(session_factory=isolated_sessions)


def test_empty_invite_install_requires_an_actual_invite_code(tmp_path, monkeypatch):
    _, isolated_sessions = _isolated_user_sessions(tmp_path, "invite-bootstrap.db")
    monkeypatch.setattr(settings, "allow_registration", "invite")
    monkeypatch.setattr(settings, "admin_password", "")
    monkeypatch.setattr(settings, "invite_code", "")

    with pytest.raises(RuntimeError, match="OSS_INVITE_CODE"):
        security.validate_bootstrap_state(session_factory=isolated_sessions)

    monkeypatch.setattr(settings, "invite_code", "configured-invite")
    security.validate_bootstrap_state(session_factory=isolated_sessions)
