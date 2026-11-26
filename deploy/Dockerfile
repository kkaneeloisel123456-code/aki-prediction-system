# The deployment tool is installed outside the checkout being built.
ARG NODE_IMAGE=public.ecr.aws/docker/library/node:22-slim
ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
FROM ${NODE_IMAGE} AS frontend
WORKDIR /app
ARG NPM_CONFIG_REGISTRY=https://registry.npmjs.org/
ARG NODE_OPTIONS=--max-old-space-size=768
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci
COPY frontend ./frontend
RUN cd frontend && npm run build

FROM ${PYTHON_IMAGE} AS runtime
WORKDIR /app
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
COPY backend/requirements.txt ./backend/requirements.txt
# Installed by the deployer inside a temporary build context, never in the repository.
COPY .aki-runtime-constraints.txt /tmp/aki-runtime-constraints.txt
RUN pip install --no-cache-dir --timeout 120 -r backend/requirements.txt \
        -c /tmp/aki-runtime-constraints.txt \
    && pip check \
    && useradd --create-home --uid 10001 aki \
    && mkdir -p /data \
    && chown -R aki:aki /app /data
COPY --chown=aki:aki backend ./backend
COPY --chown=aki:aki app_data ./app_data
COPY --chown=aki:aki outputs ./outputs
COPY --chown=aki:aki scripts ./scripts
COPY --from=frontend --chown=aki:aki /app/frontend/dist ./frontend/dist
ENV PYTHONUNBUFFERED=1 PORT=8000 AKI_DB_PATH=/data/clinical.db \
    AKI_AUTH_CONFIG=/data/auth_config.json AKI_BACKUP_DIR=/data/backups
VOLUME ["/data"]
USER aki
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port 8000"]
