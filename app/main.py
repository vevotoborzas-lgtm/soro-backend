import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import account, articles, auth, billing, keywords, webhooks
from app.core.config import get_settings
from app.core.database import Base, engine, ensure_user_schema_patches
from app.core.rate_limit import limiter

settings = get_settings()
log = logging.getLogger("soro.api")


def _configure_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        )
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    # Reduce noise; request line still logged from our middleware at INFO
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        # SQLite dev: auto-create tables. PostgreSQL: run `alembic upgrade head` before deploy.
        if engine.dialect.name == "sqlite":
            await conn.run_sync(Base.metadata.create_all)
        await ensure_user_schema_patches(conn)
    yield


app = FastAPI(title="Soro.hu API", version="1.0.0", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = req_id
    log.info("%s %s", request.method, request.url.path)
    try:
        response = await call_next(request)
    except Exception:
        log.exception("request failed %s %s request_id=%s", request.method, request.url.path, req_id)
        raise
    response.headers["X-Request-ID"] = req_id
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", None)
    log.warning("validation error request_id=%s path=%s errors=%s", req_id, request.url.path, exc.errors())
    return JSONResponse(status_code=422, content={"detail": exc.errors(), "request_id": req_id})


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    req_id = getattr(request.state, "request_id", None)
    if exc.status_code >= 500:
        log.error("HTTP %s request_id=%s path=%s detail=%s", exc.status_code, req_id, request.url.path, exc.detail)
    headers = getattr(exc, "headers", None)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail, "request_id": req_id}, headers=headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, StarletteHTTPException):
        return await http_exception_handler(request, exc)
    req_id = getattr(request.state, "request_id", None)
    log.exception("unhandled error request_id=%s %s %s", req_id, request.method, request.url.path)
    body: dict = {"detail": "Internal server error", "request_id": req_id}
    if settings.environment == "development":
        body["error"] = repr(exc)
    return JSONResponse(status_code=500, content=body)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(articles.router)
app.include_router(keywords.router)
app.include_router(account.router)
app.include_router(billing.router)
app.include_router(webhooks.router)


@app.get("/")
async def root():
    return {"service": "Soro.hu API", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/v1/ping")
async def ping():
    return {"message": "ok"}
