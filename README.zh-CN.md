# oss · 自托管图片与视频存储

[**English**](./README.md) | **简体中文**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)]()
[![Vue](https://img.shields.io/badge/Vue-3.x-42b883.svg)]()
[![Docker](https://img.shields.io/badge/Docker-ready-2496ed.svg)]()

一个 Docker 一键部署的**自托管媒体存储服务**：图片维持简单直传，视频支持原文件分片上传、断点续传和 Range 拖动播放。基于 **FastAPI + Vue 3 + SQLite**，支持用户隔离、RBAC、团队空间、API Key 和私密媒体限时签名链接。

> 视频保持原文件：不使用 FFmpeg，不转码，不生成持久化封面或 HLS。浏览器能否播放取决于容器与编码组合；任何已存视频都可以下载。

---

## ✨ 特性

- 🚀 **一键部署**：`docker compose up -d`，端口、管理员密码、上传上限等全部环境变量可配
- 🔗 **短码 URL**：图片使用 `/i/{code}`，视频使用 `/v/{code}`，短码密码学随机、不可预测
- 🖼️ **多格式支持**：jpg / png / gif / webp / svg / bmp / ico / avif / tiff，**按魔数嗅探真实类型**，不信任文件名
- 🎬 **常见视频格式**：MP4/M4V、MOV、WebM、MKV、AVI、MPEG/MPG/TS、OGV、3GP、FLV、WMV，按容器头识别，不信任扩展名或客户端 MIME
- ⏯️ **断点续传与拖动播放**：默认 8 MiB 分片，支持乱序、暂停、失败重试、刷新后重新选文件续传；`/v/{code}` 支持 Range、206 与 416
- 🔐 **认证与 RBAC**：JWT 登录、`admin`/`user` 双角色、管理员密码环境变量引导、注册策略可配（开放/邀请码/关闭）
- 🔑 **API Key 鉴权**：为脚本/命令行生成鉴权 Key，可访问图片与视频 API；**明文只显示一次**（数据库仅存 SHA-256 哈希）、支持**轮换**（旧 Key 立即失效）与撤销
- 🔏 **改密**：用户自助改密（校验旧密码）；管理员可重置任意用户密码
- 👥 **用户隔离**：每个人只能看到自己的媒体；图片和视频均支持**公开/私密**
- 🏢 **团队与团队空间**：建团队、按用户名邀请成员、成员角色（拥有者/管理员/成员）、团队图片/视频分栏及私密媒体共享
- 🛠️ **管理员界面**：系统统计（用户/图片/视频/待完成上传/团队/存储）、用户与团队管理
- 🗑️ **媒体删除**：属主/管理员/团队管理员可删除有权管理的图片或视频
- ⏳ **私密媒体签名链接**：私密图片与视频均可生成限时 HMAC 签名链接，其他人无法通过猜测短码探测资源
- 🛡️ **速率限制**：登录接口按 IP+账号限速（防暴力破解）、图片接口按 IP 限速（防短码枚举）、上传按用户限速
- 🏷️ **上传命名**：图片与视频均可自定义展示名称，支持中文；未命名则回退为文件名
- 🔍 **搜索**：按名称/文件名/短码实时搜索（个人空间与团队空间均支持）
- 🔒 **安全默认值**：非 root 运行、SVG 附件式下发（防存储型 XSS）、bcrypt 密码哈希、上传大小限制
- 📦 **API 优先**：完整 REST API（后续兼容 PicGo / ShareX / uPic 客户端）
- 🖥️ **Vue 3 前端**：浅色响应式 SPA（图片 / 视频 / 团队 / 管理 / 账户），与后端同容器交付

## 📚 目录

- [快速开始](#-快速开始)
- [配置项](#-配置项)
- [API 概览](#-api-概览)
- [本地开发](#-本地开发)
- [项目结构](#-项目结构)
- [安全设计](#-安全设计)
- [路线图](#-路线图)
- [参与贡献](#-参与贡献)
- [License](#-license)

## 🚀 快速开始

**环境要求**：Docker 与 Docker Compose。

```bash
# 1. 克隆
git clone http://www.genkinet.net:10004/it_group/oss.git && cd oss

# 2. 按需调整配置（建议设置管理员密码）
cp .env.example .env
#   编辑 .env：ADMIN_PASSWORD=你的管理员密码（建议必填）
#             PORT / MAX_UPLOAD_SIZE_MB / PUBLIC_URL 等按需调整

# 3. 启动
docker compose up -d

# 4. 打开上传页
#    http://服务器IP:8080
#    用 admin / $ADMIN_PASSWORD 登录。新安装默认关闭自助注册；
#    确需公开注册时显式设置 ALLOW_REGISTRATION=open。
```

**网络模式**：默认 `bridge` 模式将宿主机端口（`PORT`）映射进容器。若需要容器直接绑定宿主机网络（如绑定指定宿主机 IP），在 `.env` 设置 `NETWORK_MODE=host`——此时 `PORT` 即容器直接监听的宿主机端口。

> host 模式下 Compose 会提示 "Published ports are discarded when using host network mode"，属正常现象。

图片、视频、未完成分片和 SQLite 都持久化在 `./data`。数据库升级保持幂等，但升级镜像前仍应备份该目录。

### 一行命令上传

```bash
TOKEN=$(curl -X POST http://服务器IP:8080/api/auth/login \
  -d "username=admin&password=你的管理员密码" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -X POST http://服务器IP:8080/api/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@截图.png" -F "name=我的封面" -F "visibility=public"
# → {"code":"Ab3xYz9Kq1","url":"http://服务器IP:8080/i/Ab3xYz9Kq1",...}
```

## ⚙️ 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8080` | 服务端口。`bridge` 模式下为宿主机映射端口；`host` 模式下为容器直接监听的宿主机端口 |
| `NETWORK_MODE` | `bridge` | 网络模式：`bridge`（默认，端口映射）或 `host`（直接使用宿主机网络） |
| `MAX_UPLOAD_SIZE_MB` | `10` | 单文件上传大小上限（MB） |
| `MAX_VIDEO_SIZE_MB` | `2048` | 单个视频原文件大小上限（MiB） |
| `VIDEO_CHUNK_SIZE_MB` | `8` | 视频分片大小（MiB）；反向代理请求体上限必须大于它 |
| `VIDEO_UPLOAD_TTL_HOURS` | `168` | 未完成上传会话的滑动有效期（默认 7 天） |
| `MAX_ACTIVE_VIDEO_UPLOADS` | `3` | 每位用户最多未完成视频会话数 |
| `MIN_FREE_SPACE_MB` | `1024` | 磁盘保留空间；不足时图片/视频写入返回 507 |
| `VIDEO_CLEANUP_INTERVAL_SECONDS` | `3600` | 清理过期/未完成视频上传的执行间隔（秒） |
| `SQLITE_BUSY_TIMEOUT_MS` | `5000` | SQLite 等待写锁释放的最长时间（毫秒） |
| `SHORT_CODE_LENGTH` | `10` | 短码长度（base62 字符，越长越难枚举） |
| `PUBLIC_URL` | *(空)* | 返回链接的前缀，如 `https://img.example.com`；留空则按请求自动推断 |
| `ADMIN_PASSWORD` | *(空)* | 首次启动自动创建/刷新 `admin` 管理员账号；留空则不创建 |
| `ALLOW_REGISTRATION` | `closed` | 注册策略：`open` 开放 / `invite` 邀请码 / `closed` 关闭；升级后仍需公开注册必须显式设为 `open` |
| `INVITE_CODE` | *(空)* | `ALLOW_REGISTRATION=invite` 时的注册邀请码 |
| `REGISTRATION_RATE_LIMIT_PER_MINUTE` | `10` | 每 IP 每分钟自助注册尝试次数 |
| `REGISTRATION_RATE_LIMIT_PER_USERNAME` | `3` | 每用户名每分钟自助注册尝试次数 |
| `JWT_SECRET` | *(空)* | JWT 签名密钥；留空则每次重启登录态失效（建议 `openssl rand -hex 32` 生成） |
| `DEFAULT_VISIBILITY` | `private` | 新上传图片的默认可见性：`private`（仅自己/团队/管理员 + 签名链接）或 `public`（任何人可访问） |
| `SIGNED_URL_TTL_SECONDS` | `86400` | 私密媒体签名链接有效期（秒） |

## 🔌 API 概览

交互式文档：`GET /docs` —— 自建**双语（中文/English）可读文档页**，含端点表、可一键复制的 curl 示例与语言切换。

除 `注册/登录/获取公开图片/健康检查` 外，所有接口都需要携带 `Authorization: Bearer <token>`（JWT 或 API Key）。API Key 也支持 `X-API-Key` 请求头。

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | `{"username","password","invite_code"?}` → 用户信息 |
| POST | `/api/auth/login` | 表单 `username` & `password` → `{access_token, user}` |
| GET | `/api/auth/me` | 当前用户信息 |
| POST | `/api/auth/change-password` | `{old_password, new_password}` 修改自己的密码 |
| GET | `/api/auth/config` | 前端可安全读取的注册模式、上传限制等配置 |

### 图片

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/upload` | multipart `file`，可选 `name`、`visibility`、`team_id`（默认私密） |
| GET | `/i/{code}` | 获取图片（公开：任何人；私密：属主/团队成员/管理员/签名链接） |
| GET | `/api/images?limit&offset&q` | 列出我的图片（管理员看全部），按名称/文件名/短码搜索 |
| PATCH | `/api/images/{code}` | 修改 `name` / `visibility`（属主/管理员/团队管理员） |
| DELETE | `/api/images/{code}` | 删除图片（属主/管理员/团队管理员） |
| GET | `/api/images/{code}/link?ttl` | 生成限时签名链接（属主/团队成员/管理员） |

### 视频与断点续传

快速指纹的算法为：分别计算文件开头、中间、末尾最多 1 MiB 的 SHA-256，再对 UTF-8 文本 `size:head_hash:middle_hash:tail_hash` 计算 SHA-256。它用于确认刷新后重新选择的是同一文件；每个分片还需单独提供 SHA-256。

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/video-uploads` | 初始化 `{filename,size,name?,visibility?,team_id?,fingerprint}`；返回 `upload_id`、`chunk_size`、`total_parts`、`uploaded_parts`、`expires_at` |
| GET | `/api/video-uploads/{upload_id}` | 查询服务端真实状态和已上传分片序号 |
| PUT | `/api/video-uploads/{upload_id}/parts/{part_number}` | 原始二进制，请求头必须含 `Content-Range` 与 `X-Chunk-SHA256`；相同内容重复提交幂等成功 |
| POST | `/api/video-uploads/{upload_id}/complete` | 校验全部分片、快速指纹和真实容器格式后原子发布 |
| DELETE | `/api/video-uploads/{upload_id}` | 取消未完成会话并清理临时文件 |
| GET | `/api/videos?limit&offset&q` | 个人视频列表（管理员查看全部） |
| PATCH | `/api/videos/{code}` | 修改 `name` / `visibility` |
| DELETE | `/api/videos/{code}` | 删除正式视频 |
| GET | `/api/videos/{code}/link?ttl` | 生成限时签名链接 |
| GET | `/v/{code}` | 播放/下载，支持 Range、206、416；`?download=1` 使用原文件名下载 |
| GET | `/api/teams/{id}/videos?q` | 团队空间视频 |

分片从 0 编号，可乱序上传。每次成功写片会刷新 7 天有效期。缺片、哈希不一致，或用同一分片号重传不同内容时返回 409；缺少或无法解析 `Content-Range` 返回 400，与对应分片不匹配的范围返回 416；其他用户无法探知该上传 ID。完整 API 示例见 `/docs`。

### 统一媒体库与分组

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/library/stats` | 当前用户个人媒体库概览；管理员返回全局概览 |
| GET | `/api/media?kind&team_id&group_id&q&limit&offset` | 图片/视频统一分页、搜索与范围筛选 |
| GET | `/api/media-groups?team_id&q&limit&offset` | 列出个人或团队分组 |
| POST | `/api/media-groups` | 创建 `{name,description?,color?,sort_order?,team_id?,codes?}`；传 `codes` 时原子创建并加入媒体 |
| GET / PATCH / DELETE | `/api/media-groups/{id}` | 查看、修改或删除分组；删除分组不会删除媒体 |
| GET / POST | `/api/media-groups/{id}/items` | 分页读取组内媒体，或用 `{codes:[...]}` 批量加入 |
| DELETE | `/api/media-groups/{id}/items/{code}` | 从分组移出媒体，不删除资产 |

### API Key 鉴权（脚本/命令行）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/keys` | 我的 Key 列表（仅前缀，绝不含完整 Key） |
| POST | `/api/keys` | 生成 Key —— **完整 Key 仅返回这一次** |
| POST | `/api/keys/{id}/rotate` | 轮换：旧 Key 立即失效，新 Key 仅显示一次 |
| DELETE | `/api/keys/{id}` | 撤销 Key |

```bash
# 用 Key 上传 / 下载 / 删除
curl -X POST http://服务器IP:8080/api/upload \
  -H "Authorization: Bearer <key>" -F "file=@a.png" -F "name=测试"
curl -o a.png "http://服务器IP:8080/i/<code>" -H "Authorization: Bearer <key>"
curl -X DELETE "http://服务器IP:8080/api/images/<code>" -H "Authorization: Bearer <key>"
```

> **安全设计**：数据库只存 SHA-256 哈希，**明文生成后无法再次查看**，只能轮换/撤销重建；Key 为 256 位密码学随机，哈希唯一约束。

### 团队

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/teams` | 创建团队（创建者为 owner） |
| GET | `/api/teams` | 我加入的团队 |
| GET | `/api/teams/{id}` | 团队详情 + 成员列表 |
| POST | `/api/teams/{id}/members` | 按用户名邀请成员 |
| PATCH | `/api/teams/{id}/members/{member_id}` | 改角色 `{role: admin\|member}`（仅 owner） |
| DELETE | `/api/teams/{id}/members/{member_id}` | 移除成员 |
| DELETE | `/api/teams/{id}` | 解散团队（媒体与未完成会话回到上传者个人空间） |
| GET | `/api/teams/{id}/images?q` | 团队空间图片（成员/管理员） |
| GET | `/api/teams/{id}/videos?q` | 团队空间视频（成员/管理员） |

> 团队内角色：`owner`（拥有者，管理一切）> `admin`（可管理成员）> `member`（可查看/上传）。团队私密图对**团队成员**可见，对团队外返回 404。

### 管理员（需全局 admin 角色）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/admin/stats` | `{users,images,videos,media_total,pending_upload_bytes,teams,storage_bytes}` |
| GET | `/api/admin/teams` | 全部团队（含拥有者、成员数） |
| GET | `/api/users` | 全部用户 |
| POST | `/api/admin/users` | 在关闭自助注册时创建 `{username,password,role?}` 用户 |
| PATCH | `/api/admin/users/{id}/role` | 设置角色 `{role: admin\|user}`（不能改自己） |
| PATCH | `/api/admin/users/{id}/password` | 重置密码 `{new_password}` |
| DELETE | `/api/admin/users/{id}` | 删除账号、个人媒体/分组、未完成上传与 Key；其拥有的团队会解散，团队媒体回到仍存在的上传者，共享分组转交或删除 |

### 获取图片与签名链接

```
GET /i/{code}[?expires=...&sig=...]
```

返回图片本体，带 `Cache-Control: public, max-age=31536000, immutable`。

- **公开**图片：任何人可访问
- **私密**图片：仅属主/团队成员/管理员（带登录令牌）或**持有有效签名链接**者可访问；其他人一律 404（不暴露存在性）
- 签名链接由 `GET /api/images/{code}/link?ttl=86400` 生成，限时有效、绑定单张图片、防伪造防重放
- 本接口按 IP 限速（默认 240 次/分钟，防短码枚举）

SVG 类图片一律以附件形式下发（`Content-Disposition: attachment` + `X-Content-Type-Options: nosniff`），浏览器不会内联渲染，防止脚本注入。

## 🛠️ 本地开发

后端（数据落在 `./data`）：

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

前端（Vite 热更新，默认代理到 `http://localhost:8000`，可用 `VITE_API_TARGET` 覆盖）：

```bash
cd frontend && npm install && npm run dev   # http://localhost:5173
```

构建前端产物（供后端/镜像托管，产物在 `frontend/dist`）：

```bash
cd frontend && npm run build
mkdir -p ../app/static && cp -r dist/* ../app/static/
```

跑测试：

```bash
pytest
```

> 前端未构建时，访问 `/` 会得到 404 提示（镜像内已内置构建产物，只有本地裸跑后端会触发）。

### 反向代理与部署注意事项

- 保持单个 Uvicorn worker。SQLite 与上传中间文件都在本机；多实例和共享对象存储不在当前范围。
- 持久化整个 `/data`，其中 `/data/uploads` 保存未完成分片。入口脚本只在首次挂载时递归初始化权限，后续启动不会扫描全部媒体文件。
- Nginx 的 `client_max_body_size` 必须大于 `VIDEO_CHUNK_SIZE_MB`（默认配置至少设为 `9m`）；不要移除 `Range`、`If-Range`、`Content-Range`、`Accept-Ranges`。Caddy 同样需要放宽请求体限制。
- 依赖下限 `starlette>=0.49.1` 包含上游 Range 解析复杂度漏洞修复；公网开放 `/v` 时请持续更新依赖。
- `/healthz` 仅做轻量存活检查；`/readyz` 还会验证 SQLite 可读、在 `/data` 完成一次可落盘且会删除的写探测，并检查磁盘保留空间。流量就绪探针应使用 `/readyz`。

### 维护窗口内的 SQLite WAL 一致备份与恢复

SQLite 数据库、`files` 下的正式媒体和 `uploads` 下的断点续传状态共同组成一份备份集。单独备份 SQLite 即使数据库内部一致，也可能引用另一个时间点已经新增或删除的媒体，因此**不能**视为服务级一致备份。

每次备份都应进入维护窗口：

1. 停止 `oss` 容器，并确认没有应用进程继续写入 `./data`。
2. 将整个 `./data` 作为一个整体进行快照、复制或归档；`oss.db`、可能存在的 `oss.db-wal`/`oss.db-shm`、`files`、`uploads` 和权限标记必须保存在同一备份集中。
3. 重启服务前验证快照/归档可读，记录或核对校验和，并确认数据库与两个媒体目录均来自这一份备份集。

恢复时保持 `oss` 停止，先校验选定备份，再整体恢复数据目录，不要逐项拼接文件。恢复 UID/GID 1000 的属主权限（真正的全新卷也可交给入口脚本初始化），启动后同时检查 `/healthz` 与 `/readyz`。禁止混用不同备份集中的数据库和媒体目录。

## 📁 项目结构

现代分层布局（core → models → schemas → services → api），按域拆分文件，最大文件约 185 行：

```
oss/
├── app/
│   ├── main.py                 # 应用入口：装配路由 + SPA 托管 + 生命周期
│   ├── core/                   # 基础设施层（无 HTTP 路由）
│   │   ├── config.py           # 环境变量配置（OSS_* 前缀）
│   │   ├── database.py         # SQLAlchemy engine/session/Base/迁移
│   │   └── security.py         # bcrypt 密码、JWT、API Key 认证、RBAC 依赖
│   ├── models/                 # ORM 模型，按域拆分
│   │   ├── user.py  api_key.py  team.py  image.py
│   ├── schemas/                # Pydantic 模型，按域拆分
│   │   ├── auth.py  image.py  team.py  key.py  admin.py  meta.py
│   ├── services/               # 业务逻辑
│   │   ├── images.py           # 魔数嗅探 + 上传/删除
│   │   ├── signing.py          # 短码 URL + 限时签名链接
│   │   ├── teams.py  shortcode.py  ratelimit.py
│   ├── api/                    # HTTP 层
│   │   ├── deps.py             # 统一依赖出口
│   │   └── routes/             # 按资源拆分的路由
│   │       ├── auth.py  users.py  upload.py  gallery.py
│   │       ├── images.py  keys.py  admin.py
│   │       └── teams/          # team.py  members.py  space.py
│   └── static/                 # 前端构建产物（Docker 多阶段注入）
├── frontend/                   # Vue 3 + Vite 前端源码
│   ├── src/
│   │   ├── App.vue             # 导航壳 + 视图切换
│   │   ├── components/         # 按视图拆分的组件
│   │   ├── api.js              # fetch 封装 + token 管理
│   │   └── style.css
│   ├── vite.config.js  package.json
├── tests/                      # pytest，按域拆分
├── Dockerfile                  # 多阶段：node 构建前端 → python 运行时
├── docker-compose.yml
└── .env.example
```

## 🔐 安全设计

- **不信任任何客户端输入**：文件类型一律按魔数（magic bytes）嗅探，文件名只作展示
- **SVG = 潜在 XSS**：始终以附件下发，禁止内联渲染
- **认证**：密码 bcrypt 哈希存储；JWT 签名（HS256）；`JWT_SECRET` 建议显式配置
- **用户隔离**：列表接口强制按属主过滤；私密图对他人返回 404（不暴露存在性）
- **私密图访问控制**：只能通过（a）属主/团队成员/管理员登录态，或（b）**限时签名链接**访问。签名 = HMAC-SHA256(code:expires)，绑定单图、防伪造、防重放、到期失效——猜测短码或截获旧链接都无法访问
- **速率限制**（内存固定窗口，单容器适用；多副本需换共享存储）：
  - 登录：每 IP 20 次/分 + 每账号 5 次/分（防暴力破解）
  - 取图 `GET /i/{code}`：每 IP 240 次/分（防短码枚举）
  - 上传：每用户 60 次/分
- **注册策略**：默认关闭，可显式切换邀请码/开放模式；管理员可通过控制台或 API 创建用户
- **随机短码**：`secrets.randbelow` 均匀采样 base62（默认 10 位 ≈ 8.4×10¹⁷），防顺序枚举
- **最小权限**：容器内以非 root 用户运行，数据卷权限由 entrypoint 自动修复
- 上传有大小上限，按块读取，超限即断

## 🗺️ 路线图

- [x] MVP：上传 API、短码 URL、SQLite、Docker 部署
- [x] 前端升级：Vue 3 + Vite SPA，多阶段构建单容器交付
- [x] 认证与角色：JWT 登录、admin/user、注册策略（开放/邀请码）、管理员密码环境变量
- [x] 多租户隔离：用户独立命名空间，图片 private/public，私有图仅本人可见
- [x] 上传命名 + 画廊搜索
- [x] 鉴权增强：私密图限时签名链接（HMAC 防伪造/重放）、登录/取图/上传速率限制
- [x] 团队与团队空间：建队、邀请成员、角色管理、团队共享图片库
- [x] 管理员界面：统计、用户角色管理、团队总览、图片删除
- [x] API Key 鉴权（明文仅显示一次、哈希存储、轮换/撤销）与密码管理
- [ ] 群组邀请码 / 公开团队加入
- [ ] 图片管理增强：批量操作、按可见性筛选
- [ ] S3 兼容 API（对接 PicGo / ShareX / uPic 截图客户端）
- [ ] S3/MinIO 存储后端适配层
- [ ] HTTPS：Caddy 反代一键启用（自动续期证书）
- [ ] CI：GitHub Actions 自动构建并推送 GHCR / Docker Hub

## 🤝 参与贡献

欢迎提交 Pull Request。请保持测试通过（`pytest`）且前端可构建（`npm --prefix frontend run build`）。重大改动建议先开 issue 讨论。

## 📄 License

[MIT](./LICENSE) © 2026 oss contributors
