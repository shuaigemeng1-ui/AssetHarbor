"""FastAPI application entry point.

Serves both the API and the built Vue 3 SPA from ``app/static`` (populated by
the Docker multi-stage build, or by `npm --prefix frontend run build` + copy).

Layered layout:
    core/      — config, database, security (no HTTP routes)
    models/    — ORM models (one module per domain)
    schemas/   — Pydantic models (one module per domain)
    services/  — business logic (upload, teams, signing, rate limit)
    api/       — HTTP layer: deps.py + routes (teams split into a package)
"""

import asyncio
import logging
import os
import tempfile
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from .api.routes import admin, auth, gallery, images, keys, library, teams, upload, users, videos
from .core.config import settings
from .core.database import SessionLocal, init_db
from .core.request_logging import RequestLogMiddleware
from .core.security_headers import SecurityHeadersMiddleware
from .core.security import ensure_admin, validate_bootstrap_state
from .schemas import HealthResponse
from .services.library import cleanup_orphan_media_library
from .services.traffic import shutdown_traffic_recorder
from .services.videos import cleanup_expired_uploads, ensure_free_space, recover_finalizing_uploads

STATIC_DIR = Path(__file__).resolve().parent / "static"
logger = logging.getLogger(__name__)
# The application emits one deliberately minimal request record. Disable
# Uvicorn's duplicate access logger, which may include the raw query string.
logging.getLogger("uvicorn.access").disabled = True

# Readiness performs real SQLite and durable filesystem writes. Keep those
# probes single-flight and briefly cache both success and failure so an exposed
# endpoint cannot amplify concurrent health checks into writer-lock/fsync load.
_READINESS_CACHE_SECONDS = 3.0
_readiness_lock = threading.Lock()
_readiness_cache: tuple[float, str | None] | None = None


async def _cleanup_uploads_periodically(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=settings.video_cleanup_interval_seconds)
        except TimeoutError:
            try:
                await asyncio.to_thread(cleanup_expired_uploads)
            except Exception:
                # Cleanup is best-effort; a transient filesystem/SQLite error
                # must not permanently stop future hourly sweeps.
                logger.exception("video upload cleanup failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_admin()
    validate_bootstrap_state()
    if settings.forwarded_allow_ips.strip() in ("", "127.0.0.1"):
        # The default only trusts localhost. A reverse proxy on another host
        # or container (e.g. a Docker bridge gateway) is then untrusted:
        # Uvicorn keeps the proxy's address, so every proxied client shares
        # one rate-limit bucket and per-IP protections lose their meaning.
        logger.warning(
            "FORWARDED_ALLOW_IPS is %r. If this service runs behind a reverse "
            "proxy on another host or container, set it to that proxy's IP or "
            "CIDR so per-client rate limits work as intended.",
            settings.forwarded_allow_ips.strip(),
        )
    cleanup_orphan_media_library()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    recover_finalizing_uploads()
    cleanup_expired_uploads()
    stop = asyncio.Event()
    cleanup_task = asyncio.create_task(_cleanup_uploads_periodically(stop))
    try:
        yield
    finally:
        stop.set()
        await cleanup_task
        await asyncio.to_thread(shutdown_traffic_recorder)


app = FastAPI(
    title="oss",
    version=settings.version,
    description="Self-hosted image and video media library with short-code URLs, "
    "resumable uploads, personal/team collections, per-user isolation and "
    "role-based access control. "
    "Images use POST /api/upload and GET /i/{code}; videos use the "
    "/api/video-uploads flow and GET /v/{code}.",
    lifespan=lifespan,
    docs_url=None,  # replaced by the custom bilingual docs page at /docs
    redoc_url=None,
)
app.add_middleware(RequestLogMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(gallery.router)
app.include_router(images.router)
app.include_router(users.router)
app.include_router(teams.router)
app.include_router(admin.router)
app.include_router(keys.router)
app.include_router(videos.router)
app.include_router(library.router)

# FastAPI correctly exposes the JWT/API-Key OR schemes from dependencies, but
# optional security dependencies still omit the anonymous alternative. These
# four public operations explicitly allow `{}` while retaining authenticated
# variants for private owner/team access in generated clients.
_ANONYMOUS_MEDIA_OPERATIONS = frozenset(
    {
        ("/i/{code}", "get"),
        ("/v/{code}", "get"),
        ("/api/media/{code}", "get"),
        ("/api/media/{code}/link", "get"),
    }
)
_default_openapi = app.openapi


def _openapi_with_optional_media_auth():
    schema = _default_openapi()
    for path, method in _ANONYMOUS_MEDIA_OPERATIONS:
        operation = schema.get("paths", {}).get(path, {}).get(method)
        if operation is None:
            continue
        declared = operation.setdefault("security", [])
        if {} not in declared:
            declared.insert(0, {})
    return schema


app.openapi = _openapi_with_optional_media_auth

if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _serve_index() -> FileResponse:
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(
        status_code=404,
        detail="frontend not built; run `npm --prefix frontend run build` "
        "and copy frontend/dist to app/static (or just use the Docker image)",
    )


@app.get("/healthz", response_model=HealthResponse, tags=["meta"])
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", version=settings.version)


def _probe_data_directory() -> None:
    """Durably write and remove a tiny readiness probe in the data volume."""
    probe_path: Path | None = None
    descriptor: int | None = None
    failure: OSError | None = None
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        descriptor, raw_path = tempfile.mkstemp(prefix=".readyz-", dir=settings.data_dir)
        probe_path = Path(raw_path)
        if os.write(descriptor, b"ready") != 5:
            raise OSError("short readiness probe write")
        os.fsync(descriptor)
    except OSError as exc:
        failure = exc
    finally:
        if descriptor is not None:
            try:
                os.close(descriptor)
            except OSError as exc:
                failure = failure or exc
        if probe_path is not None:
            try:
                probe_path.unlink(missing_ok=True)
            except OSError as exc:
                failure = failure or exc
    if failure is not None:
        raise failure


def _probe_database_write() -> None:
    """Acquire SQLite's writer lock, execute a zero-row write, then roll back."""
    with SessionLocal() as db:
        try:
            db.execute(text("BEGIN IMMEDIATE"))
            db.execute(text("UPDATE users SET id = id WHERE 0"))
        finally:
            # Rollback is required even when the probe fails so readiness never
            # changes rows or leaves a writer lock behind.
            db.rollback()


def _run_readiness_probe() -> str | None:
    """Return a public failure detail, or ``None`` when every probe succeeds."""
    try:
        _probe_database_write()
    except Exception as exc:
        logger.warning("readiness database probe failed: %s", exc)
        return "database is not ready"

    try:
        _probe_data_directory()
        ensure_free_space()
    except Exception as exc:
        logger.warning("readiness storage probe failed: %s", exc)
        return "storage is not ready"
    return None


def _cached_readiness_failure() -> str | None:
    """Run at most one probe per cache window, including failed probes."""
    global _readiness_cache
    with _readiness_lock:
        now = time.monotonic()
        if _readiness_cache is not None:
            expires_at, failure = _readiness_cache
            if now < expires_at:
                return failure
        failure = _run_readiness_probe()
        _readiness_cache = (time.monotonic() + _READINESS_CACHE_SECONDS, failure)
        return failure


def _reset_readiness_cache() -> None:
    """Clear process-local probe state (used by deterministic tests)."""
    global _readiness_cache
    with _readiness_lock:
        _readiness_cache = None


@app.get("/readyz", response_model=HealthResponse, tags=["meta"])
def readyz() -> HealthResponse:
    """Readiness: cached single-flight SQLite and data-volume write probes."""
    failure = _cached_readiness_failure()
    if failure is not None:
        raise HTTPException(status_code=503, detail=failure)
    return HealthResponse(status="ready", version=settings.version)


# Custom bilingual (中文/English) API documentation — replaces the built-in Swagger UI.
@app.get("/docs", include_in_schema=False, tags=["meta"])
def docs_page() -> FileResponse:
    page = STATIC_DIR / "docs.html"
    if page.is_file():
        return FileResponse(page)
    raise HTTPException(status_code=404, detail="docs page not built")


# SPA fallback: every non-API GET path serves the built frontend, enabling
# client-side routing. Must be registered last. Unknown API routes keep
# returning real 404 JSON instead of the SPA.
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    if full_path.startswith(("api/", "static/")):
        raise HTTPException(status_code=404, detail="not found")
    return _serve_index()
