# oss · Self-hosted Image & Video Hosting

**English** | [简体中文](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)]()
[![Vue](https://img.shields.io/badge/Vue-3.x-42b883.svg)]()
[![Docker](https://img.shields.io/badge/Docker-ready-2496ed.svg)]()

A self-hosted media service for images and original video files. Videos use resumable, out-of-order chunk uploads and HTTP Range playback; images keep their simple direct-upload flow. Built with **FastAPI + Vue 3 + SQLite** with user isolation, RBAC, teams, API-key auth, and expiring signed links.

> Videos are stored as-is: no FFmpeg, transcoding, persistent thumbnails, or HLS. Browser playback depends on the container/codec; every stored video remains downloadable.

---

## ✨ Features

- 🚀 **One-command deploy**: `docker compose up -d`; port, admin password, upload limits and more are configurable via environment variables
- 🔗 **Short-code URLs**: images use `/i/{code}` and videos use `/v/{code}`; codes are cryptographically random and unguessable
- 🖼️ **Multi-format**: jpg / png / gif / webp / svg / bmp / ico / avif / tiff, with **magic-byte sniffing** — filenames are never trusted
- 🎬 **Original video storage**: MP4/M4V, MOV, WebM, MKV, AVI, MPEG/MPG/TS, OGV, 3GP, FLV and WMV, identified from container headers rather than filename/MIME
- ⏯️ **Resumable upload & playback**: 8 MiB chunks, pause/retry/resume after refresh, integrity hashes, and RFC Range responses for seeking or partial downloads
- 🔐 **Auth & RBAC**: JWT login, `admin`/`user` roles, admin bootstrapped from an env variable, configurable registration policy (open / invite / closed)
- 🔑 **API keys**: scripts and CLIs can use both image and video APIs; **plaintext is shown exactly once** (DB stores only SHA-256 hashes), with rotation and revocation
- 🔏 **Password management**: self-service password change (verifies the old password); admins can reset any user's password
- 👥 **User isolation**: everyone sees only their own media; images and videos can both be `public` or `private`
- 🏢 **Teams & team spaces**: create teams, invite members, assign roles, and manage separate image/video tabs with private media shared inside the team
- 🛠️ **Admin dashboard**: users, images, videos, pending uploads, teams and storage statistics, plus user and team management
- 🗑️ **Media deletion**: owners, admins and team managers can delete media they manage
- ⏳ **Signed links for private media**: both private images and videos support expiring HMAC-signed links; guessing a short code does not disclose the resource
- 🛡️ **Rate limiting**: login throttled per IP + per account (anti brute-force), image fetch per IP (anti enumeration), upload per user
- 🏷️ **Upload naming**: give images and videos custom display names (Chinese supported); falls back to the filename
- 🔍 **Search**: real-time search by name / filename / short code (personal space and team spaces)
- 🔒 **Secure by default**: non-root container, SVG served as attachment (stored-XSS protection), bcrypt password hashing, upload size limits
- 📦 **API-first**: complete REST API (PicGo / ShareX / uPic compatibility planned)
- 🖥️ **Vue 3 SPA**: responsive light UI (Images / Videos / Teams / Admin / Account), delivered in the same container via multi-stage build

## 📚 Table of Contents

- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [API Overview](#-api-overview)
- [Local Development](#-local-development)
- [Project Structure](#-project-structure)
- [Security Design](#-security-design)
- [Roadmap](#-roadmap)
- [Contributing](#-contributing)
- [License](#-license)

## 🚀 Quick Start

**Requirements**: Docker and Docker Compose.

```bash
# 1. Clone
git clone http://www.genkinet.net:10004/it_group/oss.git && cd oss

# 2. Configure (set an admin password — recommended)
cp .env.example .env
#   Edit .env:  ADMIN_PASSWORD=your-admin-password
#               PORT / MAX_UPLOAD_SIZE_MB / PUBLIC_URL ... as needed

# 3. Start
docker compose up -d

# 4. Open the web UI
#    http://<server-ip>:8080
#    Sign in with admin / $ADMIN_PASSWORD. New installs disable self-registration.
#    Set ALLOW_REGISTRATION=open explicitly if public sign-up is intended.
```

**Network mode**: the default `bridge` mode maps the host port (`PORT`) to the container. If you need the container to bind directly to the host network (e.g. bind a specific host IP), set `NETWORK_MODE=host` in `.env` — `PORT` then becomes the host port the app listens on directly.

> Compose prints "Published ports are discarded when using host network mode" — that's expected in host mode.

Images, videos, unfinished parts, and SQLite persist under `./data`. Schema upgrades are idempotent, but back up this directory before upgrading.

### One-liner upload

```bash
TOKEN=$(curl -X POST http://<server-ip>:8080/api/auth/login \
  -d "username=admin&password=your-admin-password" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://<server-ip>:8080/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@screenshot.png" -F "name=My Cover" -F "visibility=public"
# → {"code":"Ab3xYz9Kq1","url":"http://<server-ip>:8080/i/Ab3xYz9Kq1",...}
```

## ⚙️ Configuration

| Env var | Default | Description |
|---|---|---|
| `PORT` | `8080` | Service port. In `bridge` mode: the host-mapped port; in `host` mode: the port the container listens on directly |
| `NETWORK_MODE` | `bridge` | Network mode: `bridge` (default, port mapping) or `host` (bind directly to the host network) |
| `MAX_UPLOAD_SIZE_MB` | `10` | Per-file upload size limit (MB) |
| `MAX_VIDEO_SIZE_MB` | `2048` | Maximum original video size (MiB) |
| `VIDEO_CHUNK_SIZE_MB` | `8` | Video chunk size (MiB); reverse-proxy body limit must be larger |
| `VIDEO_UPLOAD_TTL_HOURS` | `168` | Sliding lifetime of an unfinished video session |
| `MAX_ACTIVE_VIDEO_UPLOADS` | `3` | Maximum unfinished video sessions per user |
| `MIN_FREE_SPACE_MB` | `1024` | Reserved free disk space; image/video writes fail with 507 below it |
| `VIDEO_CLEANUP_INTERVAL_SECONDS` | `3600` | Interval between expired/incomplete video-upload cleanup passes |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite busy-writer wait time in milliseconds |
| `SHORT_CODE_LENGTH` | `10` | Short-code length (base62 chars; longer = harder to enumerate) |
| `PUBLIC_URL` | *(empty)* | Base prefix for returned links, e.g. `https://img.example.com`; leave empty to auto-derive from the request |
| `ADMIN_PASSWORD` | *(empty)* | Creates/refreshes the `admin` account on startup; empty = no admin bootstrapped |
| `ALLOW_REGISTRATION` | `closed` | Registration policy: `open` / `invite` / `closed`; upgrades that need public sign-up must explicitly set `open` |
| `INVITE_CODE` | *(empty)* | Invite code required when `ALLOW_REGISTRATION=invite` |
| `REGISTRATION_RATE_LIMIT_PER_MINUTE` | `10` | Self-registration attempts per IP per minute |
| `REGISTRATION_RATE_LIMIT_PER_USERNAME` | `3` | Self-registration attempts per username per minute |
| `JWT_SECRET` | *(empty)* | JWT signing secret; empty = ephemeral (all sessions reset on restart). Use `openssl rand -hex 32` |
| `DEFAULT_VISIBILITY` | `private` | Default visibility for new uploads: `private` (only you/team/admins + signed links) or `public` (anyone with the link) |
| `SIGNED_URL_TTL_SECONDS` | `86400` | TTL of expiring signed links for private media (seconds) |

## 🔌 API Overview

Interactive documentation: a readable bilingual (中文/English) page at `GET /docs` — endpoint tables, curl examples with one-click copy, and a language toggle.

All endpoints except register / login / public image fetch / health require `Authorization: Bearer <token>` (JWT or API key). API keys are also accepted via the `X-API-Key` header.

### Auth

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | `{"username","password","invite_code"?}` → user |
| POST | `/api/auth/login` | form `username` & `password` → `{access_token, user}` |
| GET | `/api/auth/me` | current user |
| POST | `/api/auth/change-password` | `{old_password, new_password}` |
| GET | `/api/auth/config` | non-sensitive UI config: registration mode and upload limits |

### Images

| Method | Path | Description |
|---|---|---|
| POST | `/api/upload` | multipart `file`, optional `name`, `visibility`, `team_id` (defaults to private) |
| GET | `/i/{code}` | fetch image (public: anyone; private: owner/team/admin/signed link) |
| GET | `/api/images?limit&offset&q` | list my images (admins see all), search by name/filename/code |
| PATCH | `/api/images/{code}` | update `name` / `visibility` (owner/admin/team-manager) |
| DELETE | `/api/images/{code}` | delete (owner/admin/team-manager) |
| GET | `/api/images/{code}/link?ttl` | expiring signed link (owner/admin/team-member) |

### Videos

Compute SHA-256 for up to 1 MiB at the start, middle, and end, then set `fingerprint` to `SHA256(UTF-8(size:first_sha256:middle_sha256:last_sha256))`. It prevents selecting a different local file when resuming; each chunk additionally has its own SHA-256.

| Method | Path | Description |
|---|---|---|
| POST | `/api/video-uploads` | initialize `{filename,size,name?,visibility?,team_id?,fingerprint}`; returns `upload_id`, `chunk_size`, `total_parts`, `uploaded_parts`, `expires_at` |
| GET | `/api/video-uploads/{upload_id}` | authoritative status and uploaded part numbers |
| PUT | `/api/video-uploads/{upload_id}/parts/{part_number}` | raw bytes with `Content-Range` and `X-Chunk-SHA256`; identical replay is idempotent |
| POST | `/api/video-uploads/{upload_id}/complete` | verify all parts, fingerprint and real container type, then atomically publish |
| DELETE | `/api/video-uploads/{upload_id}` | cancel an unfinished session and remove its temporary data |
| GET | `/api/videos?limit&offset&q` | list personal videos (admins see all) |
| PATCH | `/api/videos/{code}` | update `name` / `visibility` |
| DELETE | `/api/videos/{code}` | delete the stored video |
| GET | `/api/videos/{code}/link?ttl` | create a signed link |
| GET | `/v/{code}` | stream/download, including `Range`, 206 and 416; add `?download=1` for attachment |
| GET | `/api/teams/{id}/videos?q` | team-space videos |

Example part upload (for an 8-byte file split into a 4-byte first part):

```bash
curl -X PUT "$BASE/api/video-uploads/$UPLOAD_ID/parts/0" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Range: bytes 0-3/8" \
  -H "X-Chunk-SHA256: $(sha256sum part-0 | cut -d' ' -f1)" \
  -H "Content-Type: application/octet-stream" --data-binary @part-0
```

Part numbers are zero-based and may arrive out of order. A successful part refreshes the seven-day expiry. Completion returns the final video record. Missing parts, a mismatched hash, or replaying one part number with different bytes returns 409. A missing/malformed `Content-Range` returns 400; a range that does not match the requested part returns 416. Another user's upload ID is not disclosed.

### Unified library and groups

| Method | Path | Description |
|---|---|---|
| GET | `/api/library/stats` | current personal-library overview; global overview for admins |
| GET | `/api/media?kind&team_id&group_id&q&limit&offset` | unified, searchable image/video listing |
| GET | `/api/media-groups?team_id&q&limit&offset` | list personal or team groups |
| POST | `/api/media-groups` | create `{name,description?,color?,sort_order?,team_id?,codes?}`; `codes` atomically creates and adds media |
| GET / PATCH / DELETE | `/api/media-groups/{id}` | view, update, or delete a group without deleting its media |
| GET / POST | `/api/media-groups/{id}/items` | paginate group media or add `{codes:[...]}` |
| DELETE | `/api/media-groups/{id}/items/{code}` | remove media from a group without deleting the asset |

### API keys

| Method | Path | Description |
|---|---|---|
| GET | `/api/keys` | my keys (prefix only — never the full key) |
| POST | `/api/keys` | create key — **full key returned exactly once** |
| POST | `/api/keys/{id}/rotate` | rotate: old key revoked instantly, new key shown once |
| DELETE | `/api/keys/{id}` | revoke |

```bash
# Upload / download / delete with an API key
curl -X POST http://<server-ip>:8080/api/upload \
  -H "Authorization: Bearer <key>" -F "file=@a.png" -F "name=test"
curl -o a.png "http://<server-ip>:8080/i/<code>" -H "Authorization: Bearer <key>"
curl -X DELETE "http://<server-ip>:8080/api/images/<code>" -H "Authorization: Bearer <key>"
```

### Teams

| Method | Path | Description |
|---|---|---|
| POST | `/api/teams` | create team (creator becomes owner) |
| GET | `/api/teams` | my teams |
| GET | `/api/teams/{id}` | team detail + members |
| POST | `/api/teams/{id}/members` | invite member `{username}` |
| PATCH | `/api/teams/{id}/members/{member_id}` | change role `{role: admin\|member}` (owner only) |
| DELETE | `/api/teams/{id}/members/{member_id}` | remove member |
| DELETE | `/api/teams/{id}` | disband team (media and pending sessions return to their uploaders) |
| GET | `/api/teams/{id}/images?q` | team space images (members/admins) |
| GET | `/api/teams/{id}/videos?q` | team space videos (members/admins) |

### Admin (global `admin` role)

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/stats` | `{users,images,videos,media_total,pending_upload_bytes,teams,storage_bytes}` |
| GET | `/api/admin/teams` | all teams with member counts |
| GET | `/api/users` | all users |
| POST | `/api/admin/users` | create `{username,password,role?}` while self-registration is closed |
| PATCH | `/api/admin/users/{id}/role` | set role `{role: admin\|user}` (cannot change self) |
| PATCH | `/api/admin/users/{id}/password` | reset password `{new_password}` |
| DELETE | `/api/admin/users/{id}` | delete the account, personal media/groups, pending uploads and keys; owned teams are dissolved, their media returns to surviving uploaders, and shared groups are transferred or removed |

## 🛠️ Local Development

Backend (data lands in `./data`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Frontend (Vite HMR, proxied to `http://localhost:8000`; override with `VITE_API_TARGET`):

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

Build the frontend (outputs to `frontend/dist`; copy into `app/static` to serve from the backend locally):

```bash
cd frontend && npm run build
mkdir -p ../app/static && cp -r dist/* ../app/static/
```

Tests:

```bash
pytest
```

> Visiting `/` before the frontend is built returns a 404 hint (the Docker image ships with the built frontend; only bare-backend local runs are affected).

### Reverse proxy and deployment notes

- Keep exactly one Uvicorn worker. SQLite and incomplete upload files are local; multi-instance/shared-object-storage deployment is outside this release.
- Persist all of `/data`, including `/data/uploads`. The entrypoint initializes ownership once and then avoids recursively changing a large volume on every restart.
- For Nginx, set `client_max_body_size` above `VIDEO_CHUNK_SIZE_MB` (for the default use at least `9m`) and do not strip `Range`, `If-Range`, `Content-Range`, or `Accept-Ranges`. Apply the equivalent request-body setting in Caddy.
- The dependency floor `starlette>=0.49.1` includes the upstream fix for quadratic `Range` parsing. Keep dependencies updated when exposing `/v` publicly.
- `/healthz` is a lightweight liveness check. `/readyz` additionally verifies SQLite readability, a durable write/remove probe in `/data`, and the configured free-space reserve; point traffic readiness checks at `/readyz`.

### Maintenance-window backup and restore (SQLite WAL)

The SQLite database, completed media under `files`, and resumable-upload state under `uploads` form one backup set. A database-only SQLite backup can be internally consistent while still referring to media that was added or removed at a different time, so it is **not** a consistent service backup.

Use a maintenance window for every backup:

1. Stop the `oss` container and confirm that no application process is writing to `./data`.
2. Snapshot, copy, or archive the **entire** `./data` directory as one unit. Keep `oss.db`, `oss.db-wal`, `oss.db-shm` (when present), `files`, `uploads`, and the permission marker together.
3. Before restarting the service, verify that the snapshot/archive can be read, record or compare checksums, and confirm that the database and both media directories are present in the same backup set.

To restore, keep `oss` stopped, validate the selected backup before replacing data, and restore the whole data directory rather than individual files. Restore ownership to UID/GID 1000 (or let the entrypoint initialize a genuinely fresh volume), then start the container and verify both `/healthz` and `/readyz`. Never combine a database and media directories from different backup sets.

## 📁 Project Structure

A layered, domain-split layout (largest file ≈ 185 lines):

```
oss/
├── app/
│   ├── main.py                 # app assembly: routes + SPA hosting + lifespan
│   ├── core/                   # infrastructure (no HTTP routes)
│   │   ├── config.py           # settings (OSS_* env vars)
│   │   ├── database.py         # SQLAlchemy engine/session/Base/migrations
│   │   └── security.py         # bcrypt, JWT, API-key auth, RBAC deps
│   ├── models/                 # ORM models, one module per domain
│   │   ├── user.py  api_key.py  team.py  image.py
│   ├── schemas/                # Pydantic schemas, one module per domain
│   │   ├── auth.py  image.py  team.py  key.py  admin.py  meta.py
│   ├── services/               # business logic
│   │   ├── images.py           # magic-byte sniffing + upload/delete
│   │   ├── signing.py          # short-code URLs + signed links
│   │   ├── teams.py  shortcode.py  ratelimit.py
│   ├── api/                    # HTTP layer
│   │   ├── deps.py             # unified dependency surface
│   │   └── routes/             # routes by resource
│   │       ├── auth.py  users.py  upload.py  gallery.py
│   │       ├── images.py  keys.py  admin.py
│   │       └── teams/          # team.py  members.py  space.py
│   └── static/                 # built frontend (injected by Docker)
├── frontend/                   # Vue 3 + Vite source
│   ├── src/
│   │   ├── App.vue             # nav shell + views
│   │   ├── components/         # view components
│   │   ├── api.js              # fetch wrapper + token management
│   │   └── style.css
│   ├── vite.config.js  package.json
├── tests/                      # pytest, split by domain
├── Dockerfile                  # multi-stage: node build → python runtime
├── docker-compose.yml
└── .env.example
```

## 🔐 Security Design

- **Never trust client input**: file types are sniffed from magic bytes; filenames are display-only
- **SVG = potential stored XSS**: always served as an attachment, never rendered inline
- **Auth**: bcrypt password hashes; HS256 JWT; set `JWT_SECRET` explicitly
- **User isolation**: list endpoints filter by owner; private images return 404 to others (existence is not disclosed)
- **Private-image access**: owner/team/admin login, or a **time-limited signed link** (HMAC-SHA256 over `code:expires`, bound to one image, anti-forgery/anti-replay, expires) — guessing codes or replaying old links fails
- **Rate limiting** (in-process fixed window; swap for a shared store when scaling out):
  - Login: 20/min per IP + 5/min per account (anti brute-force)
  - `GET /i/{code}`: 240/min per IP (anti enumeration)
  - Upload: 60/min per user
- **Registration policy**: closed by default, explicitly switchable to invite-only or open; admins can create accounts from the dashboard/API
- **Short codes**: `secrets.randbelow` uniform base62 sampling (10 chars ≈ 8.4×10¹⁷), no sequential enumeration
- **Least privilege**: container runs as a non-root user; data-volume permissions fixed by the entrypoint
- Uploads are read in chunks and aborted past the size limit

## 🗺️ Roadmap

- [x] MVP: upload API, short URLs, SQLite, Docker deploy
- [x] Vue 3 SPA, multi-stage single-container build
- [x] Auth & roles: JWT, admin/user, registration policy, admin password env
- [x] Multi-tenant isolation: per-user namespaces, public/private images
- [x] Upload naming + gallery search
- [x] Security hardening: signed links, rate limiting
- [x] Teams & team spaces
- [x] Admin interface + image deletion
- [x] API keys (shown once, hashed, rotate/revoke) + password management
- [ ] Team invite codes / public team joining
- [ ] Image management enhancements: batch ops, visibility filter
- [ ] S3-compatible API (PicGo / ShareX / uPic clients)
- [ ] S3/MinIO storage backend
- [ ] HTTPS: one-click Caddy reverse proxy (auto TLS)
- [ ] CI: GitHub Actions build → GHCR / Docker Hub

## 🤝 Contributing

Pull requests are welcome. Please keep tests green (`pytest`) and the frontend buildable (`npm --prefix frontend run build`). For significant changes, open an issue first to discuss.

## 📄 License

[MIT](./LICENSE) © 2026 oss contributors
