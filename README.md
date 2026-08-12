# oss · Self-hosted Image Hosting

**English** | [简体中文](./README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)]()
[![Vue](https://img.shields.io/badge/Vue-3.x-42b883.svg)]()
[![Docker](https://img.shields.io/badge/Docker-ready-2496ed.svg)]()

A self-hosted image hosting service that deploys with a single command. Upload an image, get a short-code URL instantly. Built with **FastAPI + Vue 3 + SQLite**, featuring user isolation, role-based access control (RBAC), teams & team spaces, an admin dashboard, API-key auth, and expiring signed links for private images.

> **Status: v0.5** — upload + short URLs + auth/RBAC + user isolation + teams & team spaces + admin interface + API keys & password management + signed links/rate limiting. Docker deployment ready.

---

## ✨ Features

- 🚀 **One-command deploy**: `docker compose up -d`; port, admin password, upload limits and more are configurable via environment variables
- 🔗 **Short-code URLs**: uploads return `https://your.domain/i/Ab3xYz9Kq1`, cryptographically random and unguessable
- 🖼️ **Multi-format**: jpg / png / gif / webp / svg / bmp / ico / avif / tiff, with **magic-byte sniffing** — filenames are never trusted
- 🔐 **Auth & RBAC**: JWT login, `admin`/`user` roles, admin bootstrapped from an env variable, configurable registration policy (open / invite / closed)
- 🔑 **API keys**: for scripts & CLIs — upload / download / delete images; **plaintext shown exactly once** (DB stores only SHA-256 hashes), with **rotation** (old key dies instantly) and revocation
- 🔏 **Password management**: self-service password change (verifies the old password); admins can reset any user's password
- 👥 **User isolation**: everyone sees only their own images; images are `public` or `private`, and private ones are invisible to everyone but the owner and admins
- 🏢 **Teams & team spaces**: create teams, invite members by username, member roles (owner / admin / member), a dedicated team image space, private images shared within the team
- 🛠️ **Admin dashboard**: system stats (users / images / teams / storage), user role & password management, team overview & disbanding, full image management
- 🗑️ **Image deletion**: owners, admins and team managers can delete images
- ⏳ **Signed links for private images**: private images are only reachable through **time-limited signed links** (default 24h, HMAC anti-tamper/anti-forgery/anti-replay) or by the owner/team/admin — guessing short codes or replaying old links gets nothing
- 🛡️ **Rate limiting**: login throttled per IP + per account (anti brute-force), image fetch per IP (anti enumeration), upload per user
- 🏷️ **Upload naming**: give images custom names (Chinese supported); falls back to the filename
- 🔍 **Search**: real-time search by name / filename / short code (personal space and team spaces)
- 🔒 **Secure by default**: non-root container, SVG served as attachment (stored-XSS protection), bcrypt password hashing, upload size limits
- 📦 **API-first**: complete REST API (PicGo / ShareX / uPic compatibility planned)
- 🖥️ **Vue 3 SPA**: multi-view UI (My Images / My Teams / Admin / Account), delivered in the same container via multi-stage build

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
#    Sign in with admin / $ADMIN_PASSWORD, or register a new account
#    (registration policy defaults to open)
```

Images and the SQLite database persist in `./data` — container rebuilds never lose data.

> **Upgrade note (v0.2+)**: this version added user/visibility columns. If you upgrade from v0.1 with existing data, back up and clear `data/` (`mv data data.bak`) first.

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
| `PORT` | `8080` | Host port mapped to the container (container always listens on 8080) |
| `MAX_UPLOAD_SIZE_MB` | `10` | Per-file upload size limit (MB) |
| `SHORT_CODE_LENGTH` | `10` | Short-code length (base62 chars; longer = harder to enumerate) |
| `PUBLIC_URL` | *(empty)* | Base prefix for returned links, e.g. `https://img.example.com`; leave empty to auto-derive from the request |
| `ADMIN_PASSWORD` | *(empty)* | Creates/refreshes the `admin` account on startup; empty = no admin bootstrapped |
| `ALLOW_REGISTRATION` | `open` | Registration policy: `open` / `invite` / `closed` |
| `INVITE_CODE` | *(empty)* | Invite code required when `ALLOW_REGISTRATION=invite` |
| `JWT_SECRET` | *(empty)* | JWT signing secret; empty = ephemeral (all sessions reset on restart). Use `openssl rand -hex 32` |
| `DEFAULT_VISIBILITY` | `private` | Default visibility for new uploads: `private` (only you/team/admins + signed links) or `public` (anyone with the link) |
| `SIGNED_URL_TTL_SECONDS` | `86400` | TTL of expiring signed links for private images (seconds) |

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

### Images

| Method | Path | Description |
|---|---|---|
| POST | `/api/upload` | multipart `file`, optional `name`, `visibility`, `team_id` (defaults to private) |
| GET | `/i/{code}` | fetch image (public: anyone; private: owner/team/admin/signed link) |
| GET | `/api/images?limit&offset&q` | list my images (admins see all), search by name/filename/code |
| PATCH | `/api/images/{code}` | update `name` / `visibility` (owner/admin/team-manager) |
| DELETE | `/api/images/{code}` | delete (owner/admin/team-manager) |
| GET | `/api/images/{code}/link?ttl` | expiring signed link (owner/admin/team-member) |

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
| DELETE | `/api/teams/{id}` | disband team (images return to their uploaders) |
| GET | `/api/teams/{id}/images?q` | team space images (members/admins) |

### Admin (global `admin` role)

| Method | Path | Description |
|---|---|---|
| GET | `/api/admin/stats` | `{users, images, teams, storage_bytes}` |
| GET | `/api/admin/teams` | all teams with member counts |
| GET | `/api/users` | all users |
| PATCH | `/api/admin/users/{id}/role` | set role `{role: admin\|user}` (cannot change self) |
| PATCH | `/api/admin/users/{id}/password` | reset password `{new_password}` |
| DELETE | `/api/admin/users/{id}` | delete a user and all their data (images, keys, teams) |

## 🛠️ Local Development

Backend (data lands in `./data`):

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload     # http://localhost:8080
```

Frontend (Vite HMR, proxied to the backend):

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
- **Registration policy**: open by default, switchable to invite-only or closed; admin bootstrapped from env
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
