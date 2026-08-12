# oss · 自托管图床

一个开箱即用、Docker 一键部署的**自托管图片托管服务**：上传图片，立即得到一条短码 URL。支持用户隔离、群组与角色（路线图中），后端 Python (FastAPI)。

> **Status: MVP** — 上传 + 短码链接 + 极简前端 + Docker 部署可用；多用户/RBAC/群组见[路线图](#-路线图)。

## ✨ 特性

- 🚀 **一键部署**：`docker compose up -d`，端口、上传上限等全部环境变量可配
- 🔗 **短码 URL**：上传即返回 `https://你的域名/i/Ab3xYz9Kq1`，密码学随机、不可预测
- 🖼️ **多格式支持**：jpg / png / gif / webp / svg / bmp / ico / avif / tiff，**按魔数嗅探真实类型**，不信任文件名
- 🔒 **安全默认值**：非 root 运行、SVG 附件式下发（防存储型 XSS）、上传大小限制、不可变缓存头
- 📦 **API 优先**：`POST /api/upload` 一行命令即可上传（后续兼容 PicGo / ShareX / uPic 客户端）
- 📋 **极简 Web UI**：拖拽上传、预览、一键复制链接

## 🚀 快速开始

```bash
# 1. 克隆或复制本项目
git clone <你的仓库地址> && cd oss

# 2. （可选）按需调整配置
cp .env.example .env
# 编辑 .env：端口、上传上限、公网域名等

# 3. 启动
docker compose up -d

# 4. 打开上传页
#    http://服务器IP:8080
```

图片数据和 SQLite 数据库都持久化在 `./data` 目录，容器重建不丢数据。

### 配置项

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `PORT` | `8080` | 宿主机映射端口（容器内固定 8080） |
| `MAX_UPLOAD_SIZE_MB` | `10` | 单文件上传大小上限（MB） |
| `SHORT_CODE_LENGTH` | `10` | 短码长度（base62 字符，越长越难枚举） |
| `PUBLIC_URL` | *(空)* | 返回链接的前缀，如 `https://img.example.com`；留空则按请求自动推断（`IP:端口` 访问时用它） |

## 🔌 API

### 上传图片

```
POST /api/upload
Content-Type: multipart/form-data
  file: <图片文件>
```

成功响应 `201`：

```json
{
  "code": "Ab3xYz9Kq1",
  "url": "http://192.168.1.10:8080/i/Ab3xYz9Kq1",
  "size": 123456,
  "content_type": "image/png",
  "sha256": "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
  "created_at": "2026-08-12T12:00:00Z"
}
```

错误码：`400` 空文件 · `413` 超过大小上限 · `415` 非受支持图片类型。

命令行上传示例：

```bash
curl -F "file=@截图.png" http://你的服务器:8080/api/upload
```

### 获取图片

```
GET /i/{code}
```

返回图片本体，带 `Cache-Control: public, max-age=31536000, immutable`。SVG 以附件形式下发（`Content-Disposition: attachment` + `nosniff`），避免脚本注入。

完整交互式文档见 `/docs`（Swagger UI）。

## 🛠️ 本地开发

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 启动开发服务器（数据落在 ./data）
uvicorn app.main:app --reload

# 跑测试
pytest
```

## 📁 项目结构

```
oss/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 环境变量配置（OSS_* 前缀）
│   ├── database.py          # SQLAlchemy engine / session
│   ├── models.py            # 数据模型（当前：Image）
│   ├── schemas.py           # Pydantic 响应模型
│   ├── urls.py              # 短码 URL 构建
│   ├── routers/
│   │   ├── upload.py        # POST /api/upload
│   │   └── images.py        # GET /i/{code}
│   ├── services/
│   │   ├── shortcode.py     # 密码学随机 base62 短码
│   │   └── images.py        # 魔数嗅探 + 上传落盘
│   └── static/index.html    # 极简上传页（无构建步骤）
├── tests/                   # pytest + TestClient
├── Dockerfile               # 多阶段无关、非 root、健康检查
├── docker-compose.yml
└── .env.example
```

## 🔐 安全设计

- **不信任任何客户端输入**：文件类型一律按魔数（magic bytes）嗅探，文件名只作展示
- **SVG = 潜在 XSS**：始终以附件下发，禁止内联渲染；后续接入净化器后可放开
- **随机短码**：`secrets.randbelow` 均匀采样 base62，防顺序枚举；私有图场景建议加长或用签名 URL
- **最小权限**：容器内以非 root 用户运行，数据卷权限由 entrypoint 自动修复
- 上传有大小上限，按块读取，超限即断

## 🗺️ 路线图

- [x] MVP：上传 API、短码 URL、SQLite、极简前端、Docker 部署
- [ ] 认证与角色：JWT 登录、admin/user、注册策略（开放/邀请码）、管理员密码环境变量
- [ ] 多租户隔离：用户独立命名空间，图片 private/public，私有图仅本人可见
- [ ] 群组：建组、加入、组内共享
- [ ] 前端打磨：Vue 3 SPA、画廊、拖拽增强
- [ ] S3 兼容 API（对接 PicGo / ShareX / uPic 截图客户端）
- [ ] S3/MinIO 存储后端适配层
- [ ] HTTPS：Caddy 反代一键启用（自动续期证书）
- [ ] CI：GitHub Actions 自动构建并推送 GHCR / Docker Hub

## 📄 License

[MIT](./LICENSE)
