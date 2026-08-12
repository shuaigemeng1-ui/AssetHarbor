"""Pytest fixtures.

Environment variables are set *before* importing the app so that Settings and
the SQLAlchemy engine pick up an isolated test data directory.
"""

import os
import sys
from pathlib import Path

import pytest

TEST_DATA_DIR = Path(__file__).parent / "_tmp_data"

os.environ["OSS_DATA_DIR"] = str(TEST_DATA_DIR)
os.environ["OSS_MAX_UPLOAD_SIZE_MB"] = "1"  # keep the size-limit test cheap
os.environ["OSS_SHORT_CODE_LENGTH"] = "8"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir():
    TEST_DATA_DIR.mkdir(parents=True, exist_ok=True)
    yield


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
