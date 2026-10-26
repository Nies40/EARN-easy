from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.errors import register_error_handlers
from app.api.rate_limit import AuthRateLimitMiddleware
from app.api.router import router
from app.core.body_limit import RequestBodyLimitMiddleware
from app.core.config import Settings, get_settings
from app.core.middleware import SecurityMiddleware
from app.core.rate_limit import RateLimiter, RedisRateLimiter
from app.db.permissions import check_runtime_database_role
from app.db.session import create_database_engine, create_session_factory
from app.modules.outbox.crypto import EmailPayloadCipher

FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"


def create_app(
    settings: Settings | None = None, *, rate_limiter: RateLimiter | None = None
) -> FastAPI:
    settings = settings or get_settings()
    engine = create_database_engine(settings)
    limiter = rate_limiter if rate_limiter is not None else RedisRateLimiter(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            EmailPayloadCipher(settings)
            if settings.is_production:
                check_runtime_database_role(engine, "api")
            yield
        finally:
            try:
                await limiter.aclose()
            finally:
                engine.dispose()

    app = FastAPI(
        title="Easyearn API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None if settings.is_production else "/redoc",
        openapi_url=None if settings.is_production else "/openapi.json",
    )
    app.state.settings = settings
    app.state.session_factory = create_session_factory(engine)
    app.state.rate_limiter = limiter
    app.add_middleware(RequestBodyLimitMiddleware, max_bytes=settings.max_request_body_bytes)
    app.add_middleware(AuthRateLimitMiddleware, settings=settings, limiter=limiter)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(SecurityMiddleware, settings=settings)
    register_error_handlers(app)
    app.include_router(router)

    @app.get("/", include_in_schema=False)
    @app.get("/Index.html", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(FRONTEND_ROOT / "index.html")

    app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT / "assets"), name="assets")
    return app


app = create_app()
