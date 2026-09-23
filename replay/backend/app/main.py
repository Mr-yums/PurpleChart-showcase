"""
PurpleReplay v2 — Application Entry Point
— factory FastAPI, cycle de vie (pré-chauffe des séances, arrêt propre du moteur et du
relais), handlers d'erreurs centralisés. Même patron que PurpleChart v2 (backend/app/main.py).
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator
from urllib.request import urlopen

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import ws
from app.api.routes import edge, gex, journal, market, paper, replay
from app.bootstrap import build_container
from app.core.config import AppConfig, settings
from app.core.exceptions import DomainError
from app.core.logging import get_logger, setup_logging
from app.infra.postgres import close_pools, pool
from app.visitor_workspaces import VisitorWorkspaces, WorkspaceRegistry

VERSION = "1.2.0"


def create_app(config: AppConfig | None = None) -> FastAPI:
    config = config or settings
    registry = WorkspaceRegistry(config) if os.environ.get("PR_VISITOR_WORKSPACES") == "1" else None
    setup_logging()
    log = get_logger("purplereplay")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
        catalogue = Path(config.data.archive).parent / "sessions_matview.json"
        if catalogue.exists() and not config.data.sessions_cache.exists():
            config.data.sessions_cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(catalogue, config.data.sessions_cache)
        container = build_container(config)
        app.state.container = container
        log.info("Démarrage PurpleReplay v2 (env=%s, archive=%s)", config.env, config.data.archive)
        if not config.data.archive.exists():
            log.warning("archive introuvable : %s", config.data.archive)
        container.market.prewarm()
        container.replay.start_heartbeat()
        try:
            yield
        finally:
            if registry:
                await registry.shutdown()
            await container.replay.shutdown()
            await container.hub.close_all()
            await asyncio.to_thread(close_pools)
            log.info("Arrêt PurpleReplay v2")

    app = FastAPI(
        title="PurpleReplay v2",
        version=VERSION,
        description="Replay d'entraînement orderflow — architecture POO en couches",
        lifespan=lifespan,
    )
    if registry:
        app.add_middleware(VisitorWorkspaces, registry=registry)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DomainError)
    async def _domain_handler(request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"ok": False, "detail": exc.message, "error": exc.message}
        )

    @app.exception_handler(ValueError)
    async def _value_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"ok": False, "detail": str(exc), "error": str(exc)})

    for r in (replay.router, market.router, paper.router, edge.router, gex.router, journal.router):
        app.include_router(r, prefix="/api")
    app.include_router(ws.router)

    @app.get("/api/health")
    async def health(request: Request) -> dict:
        c = request.app.state.container
        stack = {"market": "sqlite", "ticks": "python", "journal": "local"}
        if c.config.data.market_dsn:

            def check_stack():
                with pool(c.config.data.market_dsn).connection() as connection:
                    assert connection.execute("SELECT count(*) FROM public.market_imports").fetchone()[0] == 2
                with pool(c.config.data.state_dsn).connection() as connection:
                    connection.execute("SELECT 1 FROM simulation.documents LIMIT 1")
                with urlopen(c.config.data.tick_url + "/health", timeout=3) as response:
                    assert json.load(response)["status"] == "ok"

            await asyncio.to_thread(check_stack)
            stack = {"market": "postgresql", "ticks": "go", "journal": "postgresql"}
        return {
            "stack": stack,
            "status": "ok",
            "version": VERSION,
            "archive": "ok" if c.config.data.archive.exists() else "missing",
            "replay": c.replay.status(),
        }

    web_dir = os.environ.get("PR_WEB_DIR")
    if web_dir:
        from fastapi.staticfiles import StaticFiles

        app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1"])

        @app.middleware("http")
        async def response_policy(request, call_next):
            response = await call_next(request)
            response.headers.update(
                {
                    "Content-Security-Policy": "default-src 'self'; connect-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
                    "Referrer-Policy": "no-referrer",
                    "X-Content-Type-Options": "nosniff",
                    "X-Frame-Options": "DENY",
                }
            )
            return response

        app.mount("/", StaticFiles(directory=web_dir, html=True), name="frontend")
    return app


app = create_app()
