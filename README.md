# oss · 自托管图床

一个开箱即用、Docker 一键部署的**自托管图片托管服务**：上传图片，立即得到一条短码 URL。支持**用户隔离、角色权限（RBAC）**，后端 Python (FastAPI)。

> **Status: v0.2** — 上传 + 短码链接 + 认证/RBAC + 用户隔离 + 命名/搜索 + Docker 部署可用；群组见[路线图](#-路线图)。

## ✨ 特性

- 🚀 **一键部署**：`docker compose up -d`，端口、管理员密码、上传上限等全部环境变量可配
- 🔗 **短码 URL**：上传即返回 `https://你的域名/i/Ab3xYz9Kq1`，密码学随机、不可预测
- 🖼️ **多格式支持**：jpg / png / gif / webp / svg / bmp / ico / avif / tiff，**按魔数嗅探真实类型**，不信任文件名
- 🔐 **认证与 RBAC**：JWT 登录、admin/user 双角色、管理员密码环境变量引导、注册策略可配（开放/邀请码/关闭）
- 👥 **用户隔离**：每个人只能看到自己的图片；图片可分**公开/私密**，私密图仅本人与管理员可见
- 🏷️ **上传命名**：上传时可给图片自定义名称，支持中文；未命名则回退为文件名
- 🔍 **搜索**：按名称/文件名/短码实时搜索
- 🔒 **安全默认值**：非 root 运行、SVG 附件式下发（防存储型 XSS）、bcrypt 密码哈希、上传大小限制
- 📦 **API 优先**：完整 REST API（后续兼容 PicGo / ShareX / uPic 客户端）
- 🖥️ **Vue 3 前端**：SPA 登录/注册、拖拽上传、画廊、搜索、一键复制链接，与后端同容器交付（多阶段构建）

## 🚀 快速开始

```bash
# 1. 克隆或复制本项目
git clone <你的仓库地址> && cd oss

# 2. 按需调整配置（管理员密码必填建议）
cp .env.example .env
# 编辑 .env：ADMIN_PASSWORD=你的管理员密码（必填建议）
#            PORT / MAX_UPLOAD_SIZE_MB / PUBLIC_URL 等按需调整

# 3. 启动
docker compose up -d

# 4. 打开上传页，注册账号或直接用 admin 登录
#    http://服务器IP:8080
```

图片数据和 SQLite 数据库都持久化在 `./data` 目录，容器重建不丢数据。

> **v0.2 升级注意**：本版本新增了用户/可见性等字段，若从 v0.1 升级且 `data/` 里有旧数据，请先备份并清空 `data/`（`mv data data.bak`）再启动。

### 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8080` | 宿主机映射端口（容器内固定 8080） |
| `MAX_UPLOAD_SIZE_MB` | `10` | 单文件上传大小上限（MB） |
| `SHORT_CODE_LENGTH` | `10` | 短码长度（base62 字符，越长越难枚举） |
| `PUBLIC_URL` | *(空)* | 返回链接的前缀，如 `https://img.example.com`；留空则按请求自动推断 |
| `ADMIN_PASSWORD` | *(空)* | 首次启动自动创建/刷新 `admin` 管理员账号；留空则不创建 |
| `ALLOW_REGISTRATION` | `open` | 注册策略：`open` 开放 / `invite` 邀请码 / `closed` 关闭 |
| `INVITE_CODE` | *(空)* | `ALLOW_REGISTRATION=invite` 时的注册邀请码 |
| `JWT_SECRET` | *(空)* | JWT 签名密钥；留空则每次重启登录态失效（建议 `openssl rand -hex 32` 生成） |

## 🔌 API

> 除 `注册/登录/获取公开图片/健康检查` 外，所有接口都需要携带登录令牌：
> `Authorization: Bearer <access_token>`

### 认证

```
POST /api/auth/register          # JSON: {"username", "password", "invite_code"?} → 201 UserOut
POST /api/auth/login             # 表单: username & password → {access_token, user}
GET  /api/auth/me                # 当前用户信息（校验令牌是否有效）
GET  /api/users                  # 用户列表（仅 admin）
```

命令行示例：

```bash
# 注册
curl -X POST http://你的服务器:8080/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"pass123"}'

# 登录，拿到 token
TOKEN=$(curl -X POST http://你的服务器:8080/api/auth/login \
  -d "username=alice&password=pass123" | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")
```

### 上传图片（需登录）

```
POST /api/upload
Authorization: Bearer <token>
Content-Type: multipart/form-data
  file:       <图片文件>          （必填）
  name:       <显示名称>          （可选，支持中文；缺省用文件名）
  visibility: public | private    （可选，默认 public）
```

成功响应 `201`：

```json
{
  "code": "Ab3xYz9Kq1",
  "url": "http://192.168.1.10:8080/i/Ab3xYz9Kq1",
  "size": 123456,
  "content_type": "image/png",
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "created_at": "2026-08-12T12:00:00Z",
  "name": "我的封面",
  "visibility": "private",
  "owner_id": 3
}
```

错误码：`401` 未登录 · `400` 空文件 · `413` 超过大小上限 · `415` 非受支持图片类型 · `422` visibility 非法。

```bash
curl -X POST http://你的服务器:8080/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@截图.png" -F "name=我的封面" -F "visibility=public"
```

### 获取图片

```
GET /i/{code}
```

返回图片本体，带 `Cache-Control: public, max-age=31536000, immutable`。**公开**图片任何人可访问；**私密**图片仅属主与管理员可访问（他人/未登录返回 404，不暴露存在性）。SVG 以附件形式下发（`Content-Disposition: attachment` + `nosniff`），避免脚本注入。

### 列出图片（需登录，按用户隔离）

```
GET /api/images?limit=20&offset=0&q=
```

- **普通用户**：只返回自己的图片；**管理员**：返回全部（含 `owner_username` 属主信息）
- `q`：按名称 / 文件名 / 短码模糊搜索
- 最新优先

```json
{
  "items": [
    {
      "code": "Ab3xYz9Kq1",
      "url": "https://img.example.com/i/Ab3xYz9Kq1",
      "size": 123456,
      "content_type": "image/png",
      "sha256": "9f86d0...",
      "created_at": "2026-08-12T12:00:00Z",
      "name": "我的封面",
      "visibility": "private",
      "owner_id": 3,
      "original_filename": "截图.png",
      "owner_username": "alice"
    }
  ],
  "total": 42
}
```

| 参数 | 默认 | 范围 | 说明 |
|---|---|---|---|
| `limit` | `20` | 1–100 | 返回条数 |
| `offset` | `0` | ≥0 | 分页偏移 |
| `q` | *(空)* | ≤100 字符 | 搜索名称/文件名/短码 |

> `url` 字段由 `PUBLIC_URL` 环境变量控制；留空则按请求自动推断。

完整交互式文档见 `/docs`（Swagger UI，右上角 Authorize 可填入 token 直接调试）。

## 🛠️ 本地开发

后端（数据落在 `./data`）：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload     # http://localhost:8080
```

前端（Vite 热更新，已配置代理到 8080）：

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

构建前端产物（供后端/镜像托管，产物在 `frontend/dist`）：

```bash
cd frontend && npm run build
# 本地直接让后端托管时：
mkdir -p ../app/static && cp -r dist/* ../app/static/
```

跑测试：

```bash
pytest
```

> 前端未构建时，访问 `/` 会得到 404 提示（镜像内已内置构建产物，只有本地裸跑后端会触发）。

## 📁 项目结构

```
oss/
├── app/                     # Python 后端（FastAPI）
│   ├── main.py              # 应用入口 + SPA 托管
│   ├── config.py            # 环境变量配置（OSS_* 前缀）
│   ├── database.py          # SQLAlchemy engine / session
│   ├── models.py            # User / Image 模型
│   ├── schemas.py           # Pydantic 响应模型
│   ├── security.py          # bcrypt 密码、JWT、认证依赖（RBAC）
│   ├── urls.py              # 短码 URL 构建
│   ├── routers/
│   │   ├── auth.py          # 注册 / 登录 / me
│   │   ├── upload.py        # POST /api/upload（需登录、命名、可见性）
│   │   ├── gallery.py       # GET /api/images（隔离 + 搜索）
│   │   ├── images.py        # GET /i/{code}（可见性控制）
│   │   └── users.py         # GET /api/users（仅 admin）
│   ├── services/
│   │   ├── shortcode.py     # 密码学随机 base62 短码
│   │   └── images.py        # 魔数嗅探 + 上传落盘
│   └── static/              # 前端构建产物（Docker 多阶段注入）
├── frontend/                # Vue 3 + Vite 前端源码
│   ├── src/
│   │   ├── App.vue          # 登录态 / 搜索 / 上传 / 画廊
│   │   ├── components/      # AuthView / UploadDropzone / ImageResult
│   │   ├── api.js           # fetch 封装 + token 管理
│   │   └── style.css
│   ├── vite.config.js       # 含 dev 代理到后端 8080
│   └── package.json
├── tests/                   # pytest + TestClient（27 用例）
├── Dockerfile               # 多阶段：node 构建前端 → python 运行时
├── docker-compose.yml
└── .env.example
```

## 🔐 安全设计

- **不信任任何客户端输入**：文件类型一律按魔数（magic bytes）嗅探，文件名只作展示
- **SVG = 潜在 XSS**：始终以附件下发，禁止内联渲染；后续接入净化器后可放开
- **认证**：密码 bcrypt 哈希存储；JWT 签名（HS256）；`JWT_SECRET` 建议显式配置
- **用户隔离**：列表接口强制按属主过滤；私密图对他人返回 404（不暴露存在性）
- **注册策略**：默认开放，可切换邀请码/关闭模式；管理员账号由环境变量引导创建
- **随机短码**：`secrets.randbelow` 均匀采样 base62，防顺序枚举；私有图场景建议加长或用签名 URL
- **最小权限**：容器内以非 root 用户运行，数据卷权限由 entrypoint 自动修复
- 上传有大小上限，按块读取，超限即断

## 🗺️ 路线图

- [x] MVP：上传 API、短码 URL、SQLite、Docker 部署
- [x] 前端升级：Vue 3 + Vite SPA，多阶段构建单容器交付
- [x] 认证与角色：JWT 登录、admin/user、注册策略（开放/邀请码）、管理员密码环境变量
- [x] 多租户隔离：用户独立命名空间，图片 private/public，私有图仅本人可见
- [x] 上传命名 + 画廊搜索
- [ ] 群组：建组、加入、组内共享
- [ ] 图片管理：删除、批量操作、按可见性筛选
- [ ] S3 兼容 API（对接 PicGo / ShareX / uPic 截图客户端）
- [ ] S3/MinIO 存储后端适配层
- [ ] HTTPS：Caddy 反代一键启用（自动续期证书）
- [ ] CI：GitHub Actions 自动构建并推送 GHCR / Docker Hub

## 📄 License

[MIT](./LICENSE)
