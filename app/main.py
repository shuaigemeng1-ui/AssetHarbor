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

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .api.routes import admin, auth, gallery, images, keys, teams, upload, users
from .core.config import settings
from .core.database import init_db
from .core.security import ensure_admin
from .schemas import HealthResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ensure_admin()
    yield


app = FastAPI(
    title="oss",
    version=settings.version,
    description="Self-hosted image hosting with short-code URLs, per-user "
    "isolation and role-based access control. Upload via POST /api/upload, "
    "fetch via GET /i/{code}.",
    lifespan=lifespan,
    docs_url=None,  # replaced by the custom bilingual docs page at /docs
    redoc_url=None,
)

app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(gallery.router)
app.include_router(images.router)
app.include_router(users.router)
app.include_router(teams.router)
app.include_router(admin.router)
app.include_router(keys.router)

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
