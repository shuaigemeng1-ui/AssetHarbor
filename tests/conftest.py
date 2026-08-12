"""Shared fixtures and test helpers.

Environment variables are set *before* importing the app so that Settings and
the SQLAlchemy engine pick up an isolated test data directory. Plain helper
functions live here too and are imported by the domain test modules
(e.g. ``from conftest import auth, new_user``).
"""

import itertools
import os
import shutil
import sys
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).parent / "_tmp_data"

os.environ["OSS_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["OSS_MAX_UPLOAD_SIZE_MB"] = "1"  # keep the size-limit test cheap
os.environ["OSS_SHORT_CODE_LENGTH"] = "8"
os.environ["OSS_ADMIN_PASSWORD"] = "admin-pass"
os.environ["OSS_ALLOW_REGISTRATION"] = "open"
os.environ["OSS_JWT_SECRET"] = "test-secret-0123456789abcdef0123456789abcdef"
os.environ["OSS_DEFAULT_VISIBILITY"] = "public"
os.environ["OSS_SIGNED_URL_TTL_SECONDS"] = "86400"
# Rate limits defaulted very high so unrelated tests never trip them;
# dedicated tests monkeypatch individual limits down.
os.environ["OSS_LOGIN_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["OSS_LOGIN_RATE_LIMIT_PER_USERNAME"] = "100000"
os.environ["OSS_IMAGES_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["OSS_UPLOAD_RATE_LIMIT_PER_MINUTE"] = "100000"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FAKE_PNG = PNG_MAGIC + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_uids = itertools.count(1)


def _uname(prefix="user"):
    return f"{prefix}{next(_uids)}"


def register(client, username, password="pass123"):
    resp = client.post("/api/auth/register", json={"username": username, "password": password})
    assert resp.status_code == 201, resp.text
    return resp.json()


def login(client, username, password="pass123"):
    resp = client.post("/api/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def new_user(client):
    name = _uname()
    register(client, name)
    return name, login(client, name)


def upload(client, token, filename="a.png", data=None, **extra):
    fields = dict(data or {})
    fields.update(extra)
    files = {"file": (filename, FAKE_PNG, "image/png")}
    return client.post("/api/upload", headers=auth(token), data=fields or None, files=files)


def signed_link(client, token, code, ttl=None):
    url = f"/api/images/{code}/link"
    if ttl:
        url += f"?ttl={ttl}"
    resp = client.get(url, headers=auth(token))
    assert resp.status_code == 200, resp.text
    return resp.json()


def url_path(url):
    """Extract the path+query from an absolute URL: /i/CODE?expires=..&sig=.."""
    return url.split("://", 1)[-1].split("/", 1)[-1]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _fresh_data_dir():
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
