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
from routeforge.api import templates as templates_api
from routeforge.auth import LoginLimiter, bootstrap_secrets
from routeforge.cache import RenderCache
from routeforge.config import Settings
from routeforge.db.session import init_db, make_engine
from routeforge.scheduler import refresh_loop

_UNSAFE_METHODS = {"POST", "PUT", "PATCH"}


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

    app = FastAPI(title="RouteForge", lifespan=lifespan)
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

    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        session_cookie="routeforge_session",
        max_age=14 * 24 * 3600,
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    app.include_router(auth_api.router)
    app.include_router(sources_api.router)
    app.include_router(nodes_api.router)
    app.include_router(profiles_api.router)
    app.include_router(templates_api.router)
    return app
