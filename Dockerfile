# syntax=docker/dockerfile:1
FROM node:20-slim AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
RUN cd frontend && npm run build

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt \
    && useradd --create-home --uid 10001 aki \
    && mkdir -p /data \
    && chown -R aki:aki /app /data

# Explicit runtime payloads keep the image independent of repository-only
# files (tests, acceptance screenshots, Git metadata). .dockerignore still
# excludes the clinical database, its WAL/SHM files, auth_config.json and
# backups, so those can never be baked into an image layer.
COPY --chown=aki:aki backend ./backend
COPY --chown=aki:aki app_data ./app_data
COPY --chown=aki:aki outputs ./outputs
COPY --chown=aki:aki scripts ./scripts
COPY --from=frontend --chown=aki:aki /app/frontend/dist ./frontend/dist

ENV PYTHONUNBUFFERED=1 \
    PORT=8000 \
    AKI_DB_PATH=/data/clinical.db \
    AKI_AUTH_CONFIG=/data/auth_config.json \
    AKI_BACKUP_DIR=/data/backups
VOLUME ["/data"]
USER aki
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health', timeout=3)"
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
