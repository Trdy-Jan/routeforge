"""FastAPI 应用工厂。"""

import asyncio
from contextlib import asynccontextmanager, suppress

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import Session
from starlette.middleware.sessions import SessionMiddleware

from routeforge.api import auth as auth_api
from routeforge.api import nodes as nodes_api
from routeforge.api import profiles as profiles_api
from routeforge.api import sources as sources_api
from routeforge.api import subscribe as subscribe_api
from routeforge.api import templates as templates_api
from routeforge.auth import LoginLimiter, bootstrap_secrets
from routeforge.cache import RenderCache
from routeforge.config import Settings
from routeforge.db.session import init_db, make_engine
from routeforge.scheduler import refresh_loop
from routeforge.web import mount_frontend

_UNSAFE_METHODS = {"POST", "PUT", "PATCH"}


class _SchemeAwareSessionMiddleware:
    """auto 模式：HTTPS 请求下发 Secure cookie，HTTP 请求下发普通 cookie。

    scheme 来自 uvicorn；反代时需信任其 X-Forwarded-Proto（见 ROUTEFORGE_FORWARDED_ALLOW_IPS）。
    """

    def __init__(self, app, **kwargs):
        self._plain = SessionMiddleware(app, https_only=False, **kwargs)
        self._secure = SessionMiddleware(app, https_only=True, **kwargs)

    async def __call__(self, scope, receive, send):
        mw = self._secure if scope.get("scheme") in ("https", "wss") else self._plain
        await mw(scope, receive, send)


def create_app(settings: Settings, *, http_client: httpx.Client | None = None,
               start_scheduler: bool = True) -> FastAPI:
    if settings.database_url.startswith("sqlite:///"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(settings.database_url)
    init_db(engine)
    with Session(engine) as session:
        session_secret = bootstrap_secrets(session, settings.admin_password)

    client = http_client or httpx.Client(timeout=30, follow_redirects=True)
    cache = RenderCache()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(refresh_loop(engine, client, cache.invalidate)) if start_scheduler else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task
            if http_client is None:
                client.close()

    app = FastAPI(title="RouteForge", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.engine = engine
    app.state.cache = cache
    app.state.http = client
    app.state.limiter = LoginLimiter()

    @app.middleware("http")
    async def json_only(request: Request, call_next):
        if request.url.path.startswith("/api/") and request.method in _UNSAFE_METHODS:
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"detail": "请求必须是 JSON"}, status_code=415)
        return await call_next(request)

    session_options = dict(
        secret_key=session_secret,
        session_cookie="routeforge_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
    )
    if settings.cookie_secure is None:
        app.add_middleware(_SchemeAwareSessionMiddleware, **session_options)
    else:
        app.add_middleware(SessionMiddleware, https_only=settings.cookie_secure, **session_options)

    app.include_router(auth_api.router)
    app.include_router(sources_api.router)
    app.include_router(nodes_api.router)
    app.include_router(profiles_api.router)
    app.include_router(templates_api.router)
    app.include_router(subscribe_api.router)
    if settings.static_dir is not None:
        mount_frontend(app, settings.static_dir)
    return app
