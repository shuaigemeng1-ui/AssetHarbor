"""Startup configuration rejects unsafe or nonsensical numeric values."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def _settings(**overrides) -> Settings:
    # Use a deliberately unused prefix so tests do not inherit conftest's
    # process-wide OSS_* integration-test overrides.
    return Settings(
        _env_file=None,
        _env_prefix="OSS_CONFIG_VALIDATION_TEST_",
        **overrides,
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_upload_size_mb", 0),
        ("max_upload_size_mb", 1025),
        ("max_video_size_mb", 0),
        ("max_video_size_mb", 1024 * 1024 + 1),
        ("video_chunk_size_mb", 0),
        ("video_chunk_size_mb", 1025),
        ("video_upload_ttl_hours", 0),
        ("video_upload_ttl_hours", 24 * 365 + 1),
        ("max_active_video_uploads", 0),
        ("max_active_video_uploads", 1001),
        ("video_chunk_concurrency", 0),
        ("video_chunk_concurrency", 33),
        ("min_free_space_mb", -1),
        ("min_free_space_mb", 1024 * 1024 + 1),
        ("user_storage_quota_mb", -1),
        ("user_storage_quota_mb", 10_485_761),
        ("team_storage_quota_mb", -1),
        ("team_storage_quota_mb", 10_485_761),
        ("video_cleanup_interval_seconds", 0),
        ("video_cleanup_interval_seconds", 7 * 86400 + 1),
        ("sqlite_busy_timeout_ms", 0),
        ("sqlite_busy_timeout_ms", 300_001),
        ("short_code_length", 5),
        ("short_code_length", 33),
        ("token_expire_minutes", 0),
        ("token_expire_minutes", 60 * 24 * 365 + 1),
        ("signed_url_ttl_seconds", 59),
        ("signed_url_ttl_seconds", 7 * 86400 + 1),
        ("login_rate_limit_per_minute", -1),
        ("login_rate_limit_per_username", -1),
        ("registration_rate_limit_per_minute", -1),
        ("registration_rate_limit_per_username", -1),
        ("images_rate_limit_per_minute", -1),
        ("upload_rate_limit_per_minute", -1),
    ],
)
def test_invalid_numeric_settings_fail_validation(field, value):
    with pytest.raises(ValidationError):
        _settings(**{field: value})


def test_only_documented_disable_values_accept_zero():
    configured = _settings(
        min_free_space_mb=0,
        user_storage_quota_mb=0,
        team_storage_quota_mb=0,
        login_rate_limit_per_minute=0,
        login_rate_limit_per_username=0,
        registration_rate_limit_per_minute=0,
        registration_rate_limit_per_username=0,
        images_rate_limit_per_minute=0,
        upload_rate_limit_per_minute=0,
    )

    assert configured.min_free_space_mb == 0
    assert configured.user_storage_quota_bytes == 0
    assert configured.team_storage_quota_bytes == 0
    assert configured.upload_rate_limit_per_minute == 0


def test_chunk_size_cannot_exceed_video_limit():
    with pytest.raises(ValidationError, match="must not exceed"):
        _settings(max_video_size_mb=8, video_chunk_size_mb=9)


def test_invalid_visibility_fails_validation():
    with pytest.raises(ValidationError):
        _settings(default_visibility="unlisted")


def test_invalid_process_environment_fails_during_module_import(tmp_path):
    environment = os.environ.copy()
    environment["OSS_DATA_DIR"] = str(tmp_path / "invalid-config")
    environment["OSS_MAX_UPLOAD_SIZE_MB"] = "0"

    result = subprocess.run(
        [sys.executable, "-c", "import app.core.config"],
        cwd=os.fspath(Path(__file__).resolve().parents[1]),
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "ValidationError" in result.stderr
    assert "max_upload_size_mb" in result.stderr


def test_default_numeric_behavior_is_unchanged():
    configured = _settings()

    assert configured.max_upload_size_mb == 10
    assert configured.max_video_size_mb == 2048
    assert configured.video_chunk_size_mb == 8
    assert configured.video_upload_ttl_hours == 168
    assert configured.max_active_video_uploads == 3
    assert configured.video_chunk_concurrency == 3
    assert configured.min_free_space_mb == 1024
    assert configured.user_storage_quota_mb == 0
    assert configured.team_storage_quota_mb == 0
    assert configured.video_cleanup_interval_seconds == 3600
    assert configured.sqlite_busy_timeout_ms == 5000
    assert configured.short_code_length == 10
    assert configured.token_expire_minutes == 10080
    assert configured.signed_url_ttl_seconds == 86400
