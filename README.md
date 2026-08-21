# AssetHarbor · Self-hosted Image & Video Hosting

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
- 🖼️ **Multi-format**: jpg / png / gif / webp / svg / bmp / ico / avif / tiff / pdf, with **magic-byte sniffing** — filenames are never trusted
- 🎬 **Original video storage**: MP4/M4V, MOV, WebM, MKV, AVI, MPEG/MPG/TS, OGV, 3GP, FLV and WMV, identified from container headers rather than filename/MIME
- ⏯️ **Resumable upload & playback**: 8 MiB chunks, pause/retry/resume after refresh, integrity hashes, and RFC Range responses for seeking or partial downloads
- 🔐 **Auth & RBAC**: JWT login, `admin`/`user` roles, admin bootstrapped from an env variable, configurable registration policy (open / invite / closed)
- 🔑 **API keys**: scripts and CLIs can use both image and video APIs; **plaintext is shown exactly once** (DB stores only SHA-256 hashes), with rotation and revocation
- 🔏 **Password management**: self-service password change (verifies the old password); admins can reset any user's password
- 👥 **User isolation**: personal media is isolated per user, while private team media is shared with team members; images and videos can both be `public` or `private`
- 🏢 **Teams & team spaces**: create teams, invite members, assign roles, and manage separate image/video tabs with private media shared inside the team
- 🛠️ **Admin dashboard**: users, images, videos, pending uploads, teams and storage statistics, plus user and team management
- 🗑️ **Media deletion**: owners, admins and team managers can delete media they manage
- ⏳ **Signed links for private media**: both private images and videos support expiring HMAC-signed links; guessing a short code does not disclose the resource
- 🛡️ **Rate limiting**: login throttled per IP + per account (anti brute-force), image fetch per IP (anti enumeration), upload per user
- 🏷️ **Upload naming**: give images and videos custom display names (Chinese supported); falls back to the filename
- 🔍 **Search**: real-time search by name / filename / short code (personal space and team spaces)
- 🔒 **Secure by default**: non-root container, SVG served as attachment (stored-XSS protection), bcrypt password hashing, upload size limits
- 📦 **API-first**: complete REST API (PicGo / ShareX / uPic compatibility planned)
- 🖥️ **Vue 3 SPA**: minimalist responsive media workspace for images, videos, groups, teams, administration, and account management, delivered in the same container via multi-stage build

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
git clone https://github.com/shuaigemeng1-ui/AssetHarbor.git && cd AssetHarbor

# 2. Configure security (use .env.zh-CN.example for Chinese comments)
cp .env.example .env
#   Edit .env:  ADMIN_PASSWORD=your-strong-admin-password
#               JWT_SECRET=<output of: openssl rand -hex 32>
#               PORT / MAX_UPLOAD_SIZE_MB / PUBLIC_URL ... as needed

# 3. Start
docker compose up -d

# 4. Open the web UI
#    http://<server-ip>:8080
#    Sign in with admin / $ADMIN_PASSWORD. New installs disable self-registration.
#    Set ALLOW_REGISTRATION=open explicitly if public sign-up is intended.
```

With the default `ALLOW_REGISTRATION=closed`, an empty installation fails fast
if `ADMIN_PASSWORD` is missing, preventing a deployment with no usable account.
The same protection applies to `invite` mode when `INVITE_CODE` is empty. An
existing installation that already has users may leave the bootstrap password
empty; otherwise set a strong password, use `open`, or configure invite mode
and its code together.

Production deployments should also set a stable `JWT_SECRET` of at least 32
UTF-8 bytes (`openssl rand -hex 32`). Leaving it empty is only appropriate for
temporary development: every restart invalidates existing logins and private-
media signed links. Changing a configured secret has the same effect.

**Network mode**: the default `bridge` mode maps the host port (`PORT`) to the container. If you need the container to bind directly to the host network (e.g. bind a specific host IP), set `NETWORK_MODE=host` in `.env` — `PORT` then becomes the host port the app listens on directly.

> Compose prints "Published ports are discarded when using host network mode" — that's expected in host mode.

Images, videos, unfinished parts, and SQLite persist under `./data`. Schema upgrades are idempotent, but back up this directory before upgrading. The first upgrade to this security release invalidates existing JWT sessions because account-generation claims are now mandatory; users must sign in again, while API keys remain valid.

### One-liner upload

```bash
# Create an API key in the web UI (Account → keys), then:
KEY="<your-api-key>"
curl -X POST http://<server-ip>:8080/api/upload \
  -H "Authorization: Bearer $KEY" \
  -F "file=@screenshot.png" -F "name=My Cover" -F "visibility=public"
# → {"code":"Ab3xYz9Kq1","url":"http://<server-ip>:8080/i/Ab3xYz9Kq1",...}
```

## ⚙️ Configuration

Docker Compose users can copy `.env.example`; a Chinese-commented equivalent is
available as `.env.zh-CN.example`. Both templates contain the same variables,
defaults, and ordering. Direct Uvicorn runs use the corresponding `OSS_*`
variables instead, such as `OSS_ADMIN_PASSWORD` and `OSS_JWT_SECRET`.

| Env var | Default | Description |
|---|---|---|
| `ADMIN_PASSWORD` | *(empty)* | Required for a fresh closed-registration install; creates/refreshes `admin` |
| `JWT_SECRET` | *(empty)* | Required for stable production logins and signed links; non-empty values must contain at least 32 UTF-8 bytes. Use `openssl rand -hex 32` |
| `PORT` | `8080` | Service port. In `bridge` mode: the host-mapped port; in `host` mode: the port the container listens on directly |
| `NETWORK_MODE` | `bridge` | Network mode: `bridge` (default, port mapping) or `host` (bind directly to the host network) |
| `FORWARDED_ALLOW_IPS` | `127.0.0.1` | Comma-separated trusted reverse-proxy IPs/CIDRs allowed to set `X-Forwarded-*`; never use `*` unless direct access is blocked and the proxy overwrites forwarded headers |
| `MAX_UPLOAD_SIZE_MB` | `10` | Per-image limit in MiB (`1..1024`) |
| `MAX_VIDEO_SIZE_MB` | `2048` | Maximum original video size in MiB (`1..1048576`) |
| `VIDEO_CHUNK_SIZE_MB` | `8` | Chunk size in MiB (`1..1024`, not above the video limit) |
| `VIDEO_UPLOAD_TTL_HOURS` | `168` | Sliding unfinished-session lifetime (`1..8760`) |
| `MAX_ACTIVE_VIDEO_UPLOADS` | `3` | Unfinished video sessions per user (`1..1000`) |
| `VIDEO_CHUNK_CONCURRENCY` | `3` | Maximum simultaneous inbound video chunks in the single worker (`1..32`); also exposed to the frontend scheduler |
| `MIN_FREE_SPACE_MB` | `1024` | Reserved free disk space (`0..1048576`; `0` disables); writes fail with 507 below it |
| `USER_STORAGE_QUOTA_MB` | `0` | Per-user completed media plus unfinished video reservations (`0..10485760` MiB; `0` = unlimited); team media also counts for its uploader |
| `TEAM_STORAGE_QUOTA_MB` | `0` | Per-team completed media plus unfinished video reservations (`0..10485760` MiB; `0` = unlimited); team uploads must satisfy both user and team quotas |
| `VIDEO_CLEANUP_INTERVAL_SECONDS` | `3600` | Expired-upload cleanup interval in seconds (`1..604800`) |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite busy-writer wait in milliseconds (`1..300000`) |
| `SHORT_CODE_LENGTH` | `10` | Base62 short-code length (`6..32`) |
| `PUBLIC_URL` | *(empty)* | Base prefix for returned links, e.g. `https://img.example.com`; leave empty to auto-derive from the request |
| `ALLOW_REGISTRATION` | `closed` | Registration policy: `open` / `invite` / `closed`; upgrades that need public sign-up must explicitly set `open` |
| `INVITE_CODE` | *(empty)* | Invite code required when `ALLOW_REGISTRATION=invite` |
| `TOKEN_EXPIRE_MINUTES` | `10080` | Access-token lifetime (`1..525600`) |
| `LOGIN_RATE_LIMIT_PER_MINUTE` / `LOGIN_RATE_LIMIT_PER_USERNAME` | `20` / `5` | Login attempts per IP/account per minute (`0` disables; max `1000000`) |
| `REGISTRATION_RATE_LIMIT_PER_MINUTE` / `REGISTRATION_RATE_LIMIT_PER_USERNAME` | `10` / `3` | Registration attempts per IP/username per minute (`0` disables; max `1000000`) |
| `IMAGES_RATE_LIMIT_PER_MINUTE` | `240` | Public media requests per IP per minute (`0` disables; max `1000000`) |
| `UPLOAD_RATE_LIMIT_PER_MINUTE` | `60` | Upload requests per user per minute (`0` disables; max `1000000`) |
| `VIDEO_PART_RATE_LIMIT_PER_MINUTE` | `1000` | Video chunk PUT requests per account per minute (`0` disables; max `1000000`); the default leaves headroom for a 2 GiB/8 MiB upload plus retries |
| `API_KEY_MUTATION_RATE_LIMIT_PER_DAY` | `100` | API-key create/rotate/revoke operations per account per in-process fixed 24-hour window (`1..100000`); restarting the process resets this abuse guard |
| `MAX_API_KEYS_PER_USER` | `20` | Maximum active API keys owned by one user (`1..1000`) |
| `TRAFFIC_RETENTION_DAYS` | `365` | Retain UTC daily API traffic aggregates for `1..3650` days |
| `SIGNED_URL_TTL_SECONDS` | `86400` | Private-media signed-link TTL in seconds (`60..604800`) |

Numeric settings are validated during configuration import. Invalid values
raise a Pydantic `ValidationError` before the application accepts traffic.
Omitting `visibility` is a fixed API contract: image uploads and video-upload
initialization are always `public` unless the request explicitly sends `private`.
There is no deployment setting that changes this behavior.

## 🔌 API Overview

Interactive documentation: a readable bilingual (中文/English) page at `GET /docs` with request parameters, response fields and copy-ready Python 3 (default) / cURL examples for every endpoint below.

This overview only lists the endpoints your own API key can call. Create a key in the web UI under **Account → keys** — the plaintext is shown exactly once and stored only as a SHA-256 hash. Send it as `Authorization: Bearer <key>` or `X-API-Key: <key>`. Password changes, API-key governance, team/group management, user management and all `/api/admin/**` endpoints are JWT-only and are therefore not listed here. Public media reads and public metadata/link resolution do not require authentication; private-media authorization failures return 404.

```bash
# Upload / download / delete with an API key
curl -X POST http://<server-ip>:8080/api/upload \
  -H "Authorization: Bearer <key>" -F "file=@a.png" -F "name=test"
curl -o a.png "http://<server-ip>:8080/i/<code>" -H "Authorization: Bearer <key>"
curl -X DELETE "http://<server-ip>:8080/api/images/<code>" -H "Authorization: Bearer <key>"
```

### Identity & configuration

| Method | Path | Description |
|---|---|---|
| GET | `/api/auth/me` | verify the account a key belongs to → `{id, username, role, created_at}` |
| GET | `/api/auth/config` | no auth: non-sensitive UI config — registration mode, upload/session/concurrency limits and user/team quota ceilings in bytes |

### Images

| Method | Path | Description |
|---|---|---|
| POST | `/api/upload` | multipart `file`, optional `name`, `visibility`, `team_id` (`visibility` defaults to `public`) |
| GET | `/i/{code}` | fetch image (public: anyone; private: owner/team/signed link or an authorized key) |
| GET | `/api/images?limit&offset&q&scope` | list images; an API key always returns the personal space (`scope=mine`); `scope=all` is an administrator JWT-only global view |
| PATCH | `/api/images/{code}` | update `name` / `visibility` (owner/team-manager) |
| DELETE | `/api/images/{code}` | delete (owner/team-manager) |
| GET | `/api/images/{code}/link?ttl` | expiring signed link (owner/team-member) |

### Videos

Compute SHA-256 for up to 1 MiB at the start, middle, and end, then set `fingerprint` to `SHA256(UTF-8(size:first_sha256:middle_sha256:last_sha256))`. It prevents selecting a different local file when resuming; each chunk additionally has its own SHA-256.

| Method | Path | Description |
|---|---|---|
| POST | `/api/video-uploads` | initialize `{filename,size,name?,visibility?,team_id?,fingerprint}` (`visibility` defaults to `public`); returns `upload_id`, `chunk_size`, `total_parts`, `uploaded_parts`, `expires_at` |
| GET | `/api/video-uploads` | discover the current user's resumable sessions after refresh or IndexedDB loss; also returns `max_active` and `part_concurrency` |
| GET | `/api/video-uploads/{upload_id}` | authoritative status and uploaded part numbers |
| PUT | `/api/video-uploads/{upload_id}/parts/{part_number}` | raw bytes with `Content-Range` and `X-Chunk-SHA256`; identical replay is idempotent |
| POST | `/api/video-uploads/{upload_id}/complete` | verify all parts, fingerprint and real container type, then atomically publish |
| DELETE | `/api/video-uploads/{upload_id}` | cancel an unfinished session and remove its temporary data |
| GET | `/api/videos?limit&offset&q&scope` | list videos; an API key always returns the personal space (`scope=mine`); `scope=all` is an administrator JWT-only global view |
| PATCH | `/api/videos/{code}` | update `name` / `visibility` |
| DELETE | `/api/videos/{code}` | delete the stored video |
| GET | `/api/videos/{code}/link?ttl` | create a signed link |
| GET | `/v/{code}` | stream/download, including `Range`, 206 and 416; add `?download=1` for attachment |
| GET | `/api/teams/{id}/videos?q` | team-space videos |

Example part upload (for an 8-byte file split into a 4-byte first part):

```bash
curl -X PUT "$BASE/api/video-uploads/$UPLOAD_ID/parts/0" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Range: bytes 0-3/8" \
  -H "X-Chunk-SHA256: $(sha256sum part-0 | cut -d' ' -f1)" \
  -H "Content-Type: application/octet-stream" --data-binary @part-0
```

Part numbers are zero-based and may arrive out of order. A successful part refreshes the seven-day expiry. Completion returns the final video record. Missing parts, a mismatched hash, or replaying one part number with different bytes returns 409. A missing/malformed `Content-Range` returns 400; a range that does not match the requested part returns 416. Another user's upload ID is not disclosed.

### Unified media library

Media-group CRUD and item management are JWT-only control-plane operations and are not listed here.

| Method | Path | Description |
|---|---|---|
| GET | `/api/library/stats` | current personal-library overview |
| GET | `/api/media?kind&team_id&group_id&q&limit&offset` | unified, searchable image/video listing |
| GET | `/api/media/{code}` | unified metadata; anonymous public responses hide owner/team/original-filename fields, while private media require an authorized key and otherwise return 404 |
| GET | `/api/media/{code}/link?ttl` | public media resolve anonymously to the canonical URL; authorized private media return an expiring signed URL |

### Teams

Team creation, listing, details, deletion and membership changes are JWT-only. The team-space data endpoints below accept an API key and still enforce membership on every call.

| Method | Path | Description |
|---|---|---|
| GET | `/api/teams/{id}/images?q` | team space images (members) |
| GET | `/api/teams/{id}/videos?q` | team space videos (members) |

JWT-only control-plane endpoints (registration/login/password, API-key management, team governance, media groups, user management and `/api/admin/**`) remain available and are described machine-readably in the OpenAPI spec at `GET /openapi.json`.

## 🛠️ Local Development

Backend (data lands in `./data`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
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

The repository includes a GitLab release gate in `.gitlab-ci.yml`: Python 3.12
runs compile checks and pytest, Node 20 runs `npm ci`, Vitest and the production
build, and a daemonless Docker CLI job validates whitespace and Compose syntax.
Tags automatically run a real multi-stage Docker build with DinD; maintainers
can enable the same build on another pipeline with `CI_DOCKER_BUILD=1`. No job
starts the application.

> Visiting `/` before the frontend is built returns a 404 hint (the Docker image ships with the built frontend; only bare-backend local runs are affected).

### Reverse proxy and deployment notes

- Keep exactly one Uvicorn worker. SQLite and incomplete upload files are local; multi-instance/shared-object-storage deployment is outside this release.
- Persist all of `/data`, including `/data/uploads`. The entrypoint initializes ownership once and then avoids recursively changing a large volume on every restart.
- For Nginx, set `client_max_body_size` above `max(MAX_UPLOAD_SIZE_MB, VIDEO_CHUNK_SIZE_MB)` with room for multipart framing (with the defaults, use at least `12m`). Do not strip `Range`, `If-Range`, `Content-Range`, or `Accept-Ranges`; apply the equivalent body limit in Caddy.
- Set `FORWARDED_ALLOW_IPS` to only the Nginx/Caddy source IP or Docker network CIDR. Otherwise every proxied visitor may share the proxy's rate-limit identity; trusting unverified sources lets clients spoof their address.
- Signed URLs are replayable bearer credentials until expiry. Configure the reverse proxy access log to omit or redact query strings so `expires`/`sig` never reach Nginx/Caddy logs.
- Starlette is pinned to `1.3.1`, which includes the upstream multipart parser and Range hardening fixes. Keep this security baseline or a newer reviewed release when exposing media publicly.
- `/healthz` is a lightweight liveness check. `/readyz` acquires a real SQLite writer lock, performs a zero-row update and rolls it back, then performs a durable write/remove probe in `/data` and checks the free-space reserve. Probes are single-flight and cache success or failure for about three seconds to prevent health-check bursts from multiplying writes. Point traffic readiness checks at `/readyz`.
- Every response includes `X-Request-ID`. A caller-supplied ID is reused only when it matches the safe 1–64 character format; otherwise the app generates one. Request logs contain that safe request ID plus method, decoded path, status and duration—never other request headers or query parameters such as signed-link `sig`/`expires`.
- Uvicorn's default access log is disabled to avoid duplicate or query-bearing records. Compose uses Docker's bounded `local` log driver (`10m`, 3 files); adjust these limits to match the host's retention policy.

### Maintenance-window backup and restore (SQLite WAL)

The SQLite database, completed media under `files`, and resumable-upload state under `uploads` form one backup set. A database-only SQLite backup can be internally consistent while still referring to media that was added or removed at a different time, so it is **not** a consistent service backup.

Use a maintenance window for every backup:

1. Stop the `oss` container and confirm that no application process is writing to `./data`.
2. Snapshot, copy, or archive the **entire** `./data` directory as one unit. Keep `oss.db`, `oss.db-wal`, `oss.db-shm` (when present), `files`, `uploads`, and the permission marker together.
3. Before restarting the service, verify that the snapshot/archive can be read, record or compare checksums, and confirm that the database and both media directories are present in the same backup set.

To restore, keep `oss` stopped, validate the selected backup before replacing data, and restore the whole data directory rather than individual files. Restore ownership to UID/GID 1000 (or let the entrypoint initialize a genuinely fresh volume), then start the container and verify both `/healthz` and `/readyz`. Never combine a database and media directories from different backup sets.

## 📁 Project Structure

A layered layout split by domain across the backend and frontend:

```
AssetHarbor/
├── app/
│   ├── main.py                 # app assembly: routes + SPA hosting + lifespan
│   ├── core/                   # infrastructure (no HTTP routes)
│   │   ├── config.py           # settings (OSS_* env vars)
│   │   ├── database.py         # SQLAlchemy engine/session/Base/migrations
│   │   └── security.py         # bcrypt, JWT, API-key auth, RBAC deps
│   ├── models/                 # users, teams, media, uploads, groups, traffic
│   ├── schemas/                # Pydantic contracts by domain
│   ├── services/               # business logic
│   │   ├── images.py  videos.py  library.py
│   │   ├── signing.py          # short-code URLs + signed links
│   │   └── teams.py  storage_quota.py  traffic.py  ratelimit.py
│   ├── api/                    # HTTP layer
│   │   ├── deps.py             # unified dependency surface
│   │   └── routes/             # routes by resource
│   │       ├── auth.py  users.py  upload.py  gallery.py  library.py
│   │       ├── images.py  videos.py  keys.py  admin.py
│   │       └── teams/          # team.py  members.py  space.py
│   └── static/                 # built frontend (injected by Docker)
├── frontend/                   # Vue 3 + Vite source
│   ├── src/
│   │   ├── App.vue             # nav shell + views
│   │   ├── components/         # media views, cards, inspector, modals
│   │   ├── stores/             # feedback and upload state
│   │   ├── tests/              # Vitest component and state tests
│   │   ├── api.js              # fetch wrapper + token management
│   │   ├── style.css            # shared/auth styles
│   │   └── workspace.css        # authenticated workspace styles
│   ├── vite.config.js  package.json
├── tests/                      # pytest, split by domain
├── Dockerfile                  # multi-stage: node build → python runtime
├── docker-compose.yml
├── .gitlab-ci.yml              # test/build/release gate for GitLab mirrors
├── .env.example                # English Docker Compose template
└── .env.zh-CN.example          # Chinese Docker Compose template
```

## 🔐 Security Design

- **Never trust client input**: file types are sniffed from magic bytes; filenames are display-only
- **SVG = potential stored XSS**: always served as an attachment, never rendered inline
- **Auth**: bcrypt password hashes; HS256 JWT; set `JWT_SECRET` explicitly
- **User isolation**: list endpoints filter by owner; private images return 404 to others (existence is not disclosed)
- **Private-media access**: owner/team/admin login, or a **time-limited signed link** (HMAC-SHA256 over `code:expires:signing_version`, bound to one media item, tamper-resistant, revocable and expiring). A valid link is a bearer credential that can be replayed until expiry; protect it like a temporary password and prefer a short TTL.
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
- [x] GitLab CI release gate: backend tests, frontend tests/build, Compose and whitespace checks

## 🤝 Contributing

Pull requests are welcome. Please keep tests green (`pytest`) and the frontend buildable (`npm --prefix frontend run build`). For significant changes, open an issue first to discuss.

## 📄 License

[MIT](./LICENSE) © 2026 AssetHarbor contributors
