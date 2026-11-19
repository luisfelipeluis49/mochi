# Build context is the REPO ROOT (so packages/contracts is reachable):
#   docker build -f services/backend/Dockerfile -t mochi-backend .
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY packages/contracts packages/contracts
COPY services/backend/pyproject.toml services/backend/uv.lock services/backend/
WORKDIR /app/services/backend
# Dependencies first (cached layer), then the project itself, both from the lock file.
RUN uv sync --frozen --no-dev --no-editable --no-install-project
COPY services/backend/src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runtime
ARG GIT_SHA=dev
ENV PYTHONUNBUFFERED=1 GIT_SHA=${GIT_SHA} PORT=8000
RUN useradd --create-home --uid 10001 mochi
# Same absolute path as in the build stage: the venv's scripts point at it.
COPY --from=build /app/services/backend/.venv /app/services/backend/.venv
USER mochi
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s \
  CMD ["/app/services/backend/.venv/bin/python", "-c", "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT','8000'), timeout=2)"]
# ONE worker: all state (session, saved words, game) lives in this process's memory.
CMD ["sh", "-c", "exec /app/services/backend/.venv/bin/uvicorn mochi_backend.app:app_from_env --factory --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --proxy-headers --forwarded-allow-ips='*'"]
