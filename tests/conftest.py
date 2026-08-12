"""Shared fixtures and test helpers.

Environment variables are set *before* importing the app so that Settings and
the SQLAlchemy engine pick up an isolated test data directory. Plain helper
functions live here too and are imported by the domain test modules
(e.g. ``from conftest import auth, new_user``).
"""

import itertools
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

# Isolate simultaneous pytest invocations (for example focused checks running
# alongside a full suite) so their shared usernames and startup cleanup cannot
# corrupt each other's SQLite/filesystem state.
TEST_DATA_DIR = Path(tempfile.gettempdir()) / f"oss-pytest-{os.getpid()}"

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
os.environ["OSS_REGISTRATION_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["OSS_REGISTRATION_RATE_LIMIT_PER_USERNAME"] = "100000"
os.environ["OSS_IMAGES_RATE_LIMIT_PER_MINUTE"] = "100000"
os.environ["OSS_UPLOAD_RATE_LIMIT_PER_MINUTE"] = "100000"
# Keep resumable-video integration tests small while exercising the exact same
# protocol used by the 2 GiB / 8 MiB production defaults.
os.environ["OSS_MAX_VIDEO_SIZE_MB"] = "4"
os.environ["OSS_VIDEO_CHUNK_SIZE_MB"] = "1"
os.environ["OSS_VIDEO_UPLOAD_TTL_HOURS"] = "168"
os.environ["OSS_MAX_ACTIVE_VIDEO_UPLOADS"] = "100"
os.environ["OSS_MIN_FREE_SPACE_MB"] = "0"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
FAKE_PNG = PNG_MAGIC + b"\x00" * 64
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><rect width="10" height="10"/></svg>'
MP4_HEADER = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00mp41mp42"

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


def video_fingerprint(data):
    """Browser-compatible quick fingerprint used by resumable uploads."""
    sample_size = 1024 * 1024
    size = len(data)
    offsets = (0, max(0, size // 2 - sample_size // 2), max(0, size - sample_size))
    hashes = [
        hashlib.sha256(data[offset : offset + min(sample_size, size - offset)]).hexdigest()
        for offset in offsets
    ]
    return hashlib.sha256(f"{size}:{hashes[0]}:{hashes[1]}:{hashes[2]}".encode()).hexdigest()


def init_video(client, token, data, filename="clip.mp4", **overrides):
    payload = {
        "filename": filename,
        "size": len(data),
        "name": filename,
        "visibility": "public",
        "team_id": None,
        "fingerprint": video_fingerprint(data),
    }
    payload.update(overrides)
    return client.post("/api/video-uploads", headers=auth(token), json=payload)


def put_video_part(client, token, upload_id, part_number, data, start, total, **headers):
    digest = hashlib.sha256(data).hexdigest()
    request_headers = {
        **auth(token),
        "Content-Type": "application/octet-stream",
        "Content-Range": f"bytes {start}-{start + len(data) - 1}/{total}",
        "X-Chunk-SHA256": digest,
        **headers,
    }
    return client.put(
        f"/api/video-uploads/{upload_id}/parts/{part_number}",
        headers=request_headers,
        content=data,
    )


def upload_video(client, token, data=None, **overrides):
    data = data or (MP4_HEADER + b"video-test-payload")
    initialized = init_video(client, token, data, **overrides)
    assert initialized.status_code == 201, initialized.text
    info = initialized.json()
    chunk_size = info["chunk_size"]
    for number, start in enumerate(range(0, len(data), chunk_size)):
        response = put_video_part(
            client, token, info["upload_id"], number, data[start : start + chunk_size], start, len(data)
        )
        assert response.status_code == 200, response.text
    completed = client.post(
        f"/api/video-uploads/{info['upload_id']}/complete", headers=auth(token)
    )
    assert completed.status_code == 200, completed.text
    return info, completed.json()


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
