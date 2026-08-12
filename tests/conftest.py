"""Pytest fixtures.

Environment variables are set *before* importing the app so that Settings and
the SQLAlchemy engine pick up an isolated test data directory.
"""

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


@pytest.fixture(scope="session", autouse=True)
def _fresh_data_dir():
    shutil.rmtree(TEST_DATA_DIR, ignore_errors=True)
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
