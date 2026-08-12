# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OSS_DATA_DIR=/data

# gosu lets the entrypoint drop from root to the unprivileged `oss` user
# after fixing up the permissions of the mounted data volume.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu passwd \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --gid 1000 oss \
    && adduser --disabled-password --gecos "" --uid 1000 --ingroup oss oss

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --chown=oss:oss . .

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=2).status==200 else 1)"

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
