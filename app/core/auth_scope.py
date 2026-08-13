"""Request authentication scope carried with ORM user principals."""

from typing import Literal

from ..models.user import User

AuthScope = Literal["jwt", "api_key", "tenant", "internal"]
_AUTH_SCOPE_ATTRIBUTE = "_oss_auth_scope"
_ACCOUNT_IDENTITY_ATTRIBUTE = "_oss_account_identity"


def _account_identity(user: User) -> tuple[int, str] | None:
    try:
        return int(user.id), user.created_at.isoformat()
    except Exception:
        return None


def bind_auth_scope(user: User, scope: AuthScope) -> User:
    """Attach non-persistent request scope to an authenticated ORM principal."""
    setattr(user, _AUTH_SCOPE_ATTRIBUTE, scope)
    if not hasattr(user, _ACCOUNT_IDENTITY_ATTRIBUTE):
        identity = _account_identity(user)
        if identity is not None:
            setattr(user, _ACCOUNT_IDENTITY_ATTRIBUTE, identity)
    return user


def get_auth_scope(user: User) -> AuthScope:
    """Unmarked service-internal principals retain their trusted semantics."""
    scope = getattr(user, _AUTH_SCOPE_ATTRIBUTE, "internal")
    return scope if scope in ("jwt", "api_key", "tenant", "internal") else "internal"


def copy_auth_scope(source: User, target: User) -> User:
    """Preserve request scope when lifecycle code reloads a fresh ORM row."""
    setattr(target, _AUTH_SCOPE_ATTRIBUTE, get_auth_scope(source))
    identity = getattr(source, _ACCOUNT_IDENTITY_ATTRIBUTE, None)
    if identity is not None:
        setattr(target, _ACCOUNT_IDENTITY_ATTRIBUTE, identity)
    else:
        bind_auth_scope(target, get_auth_scope(source))
    return target


def get_bound_account_identity(user: User) -> tuple[int, str] | None:
    """Return the immutable identity captured when request auth succeeded."""
    identity = getattr(user, _ACCOUNT_IDENTITY_ATTRIBUTE, None)
    if (
        isinstance(identity, tuple)
        and len(identity) == 2
        and isinstance(identity[0], int)
        and isinstance(identity[1], str)
    ):
        return identity
    return None


def has_global_admin_scope(user: User | None) -> bool:
    """Only an admin JWT/internal actor receives global tenant overrides."""
    return bool(
        user is not None
        and user.role == "admin"
        and get_auth_scope(user) in ("jwt", "internal")
    )
