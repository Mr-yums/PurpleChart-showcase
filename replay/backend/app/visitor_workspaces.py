"""Un compte et un journal persistants par navigateur, archives communes en lecture seule."""

import asyncio
import copy
import re
import secrets
import shutil
import time
from http.cookies import SimpleCookie
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from app.bootstrap import build_container


class VisitorWorkspaces:
    def __init__(self, app, registry):
        self.app = app
        self.registry = registry

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] not in ("http", "websocket")
            or not scope.get("path", "").startswith(("/api/", "/ws"))
            or scope["path"] == "/api/health"
        ):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode()
        if origin and urlsplit(origin).netloc != headers.get(b"host", b"").decode():
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1008})
            return await JSONResponse({"detail": "Origine non autorisée"}, status_code=403)(
                scope, receive, send
            )
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get(b"cookie", b"").decode())
        except Exception:
            pass
        sid = cookie["pr_workspace"].value if "pr_workspace" in cookie else ""
        created = not re.fullmatch("[a-f0-9]{48}", sid)
        if created:
            sid = secrets.token_hex(24)
        if scope["type"] == "websocket" and created:
            return await send({"type": "websocket.close", "code": 1008})
        try:
            c = await self.registry.get(sid)
        except RuntimeError:
            if scope["type"] == "websocket":
                return await send({"type": "websocket.close", "code": 1013})
            return await JSONResponse(
                {"detail": "Les espaces de replay sont occupés. Réessaie dans quelques instants."},
                status_code=503,
            )(scope, receive, send)
        scope.setdefault("state", {})["visitor_container"] = c

        async def send_cookie(message):
            if message["type"] == "http.response.start":
                message.setdefault("headers", []).append(
                    (
                        b"set-cookie",
                        f"pr_workspace={sid}; Path=/; HttpOnly; SameSite=Lax; Max-Age=31536000".encode(),
                    )
                )
                message["headers"].append((b"cache-control", b"no-store"))
            await send(message)

        await self.app(scope, receive, send_cookie)


class WorkspaceRegistry:
    def __init__(self, config):
        self.config = config
        self.items = {}
        self.lock = asyncio.Lock()

    async def get(self, sid):
        async with self.lock:
            now = time.monotonic()
            if sid in self.items:
                c, _ = self.items[sid]
                self.items[sid] = (c, now)
                return c
            for key, (c, last) in list(self.items.items()):
                if not c.hub.count and now - last > 1800:
                    await c.replay.shutdown()
                    await c.hub.close_all()
                    del self.items[key]
            if len(self.items) >= 16:
                raise RuntimeError("Capacity")
            config = copy.deepcopy(self.config)
            config.data.data_dir = self.config.data.data_dir / "visitors" / sid
            config.data.data_dir.mkdir(parents=True, exist_ok=True)
            # Ces chemins restent ceux des archives distribuées, jamais ceux d’un visiteur.
            config.data.archive_path = self.config.data.archive
            config.data.gex_path = self.config.data.gex
            cache = self.config.data.sessions_cache
            if cache.exists() and not config.data.sessions_cache.exists():
                shutil.copy2(cache, config.data.sessions_cache)
            c = await asyncio.to_thread(build_container, config)
            c.market.prewarm()
            c.replay.start_heartbeat()
            self.items[sid] = (c, now)
            return c

    async def shutdown(self):
        for c, _ in self.items.values():
            await c.replay.shutdown()
            await c.hub.close_all()
        self.items.clear()
