FROM node:24-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY replay/frontend/ /build/replay/frontend/
COPY docs/ARCHITECTURE.md /build/docs/ARCHITECTURE.md
RUN npm run check && npm run build

FROM python:3.14-slim-trixie
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY replay/backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && useradd --uid 10001 --create-home replay && mkdir /state /market && chown replay:replay /state
COPY --chown=replay:replay replay/backend/app /app/app
COPY --from=frontend-build --chown=replay:replay /build/frontend/dist /web
ENV PR_DATA_DIR=/state PR_ARCHIVE_PATH=/market/replay_archive.sqlite PR_GEX_PATH=/market/gex_qqq.db PR_MODERN_ARCHIVE=/market/purplechart_v2_archive.sqlite PR_REGIMES_PATH=/market/regimes.json PR_REPLAY_MIN_SYMBOL_ROWS=1 PR_VISITOR_WORKSPACES=1 PR_WEB_DIR=/web
USER replay
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=4)"
CMD ["python","-m","uvicorn","app.main:app","--host","0.0.0.0","--port","8080","--no-access-log"]
