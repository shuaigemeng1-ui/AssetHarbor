# syntax=docker/dockerfile:1

# --- Stage 1: build the Vue 3 frontend --------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python runtime ------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OSS_DATA_DIR=/data

# gosu lets the entrypoint initialize a mounted data volume once, then drop
# privileges to the unprivileged `oss` user.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu passwd \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --gid 1000 oss \
    && adduser --disabled-password --gecos "" --uid 1000 --ingroup oss oss

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=oss:oss . .
# 注入多阶段构建产出的前端静态文件（Vite build → dist/ → app/static）
COPY --from=frontend --chown=oss:oss /build/frontend/dist /app/app/static

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,sys,urllib.request; port=os.environ.get('OSS_APP_PORT','8080'); sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:'+port+'/readyz', timeout=2).status==200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# 监听端口由环境变量 OSS_APP_PORT 控制（默认 8080）：
# bridge 网络模式由 compose 端口映射转发；host 网络模式下直接监听宿主机端口。
# Keep a single worker: resumable uploads use local SQLite and filesystem state.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${OSS_APP_PORT:-8080} --workers 1 --no-access-log --forwarded-allow-ips \"${OSS_FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
