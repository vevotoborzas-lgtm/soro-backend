import logging
import os

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# ── Config betöltés ───────────────────────────────────────────────────────────
try:
    from app.core.config import settings
    logger.info(f"Config betöltve. ENV={settings.ENVIRONMENT}")
except Exception as e:
    logger.error(f"Config hiba: {e}")
    raise

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Soro.hu backend indul...")
    try:
        from app.core.database import init_db
        await init_db()
        logger.info("Adatbázis kész.")
    except Exception as e:
        logger.error(f"DB hiba (folytatás): {e}")
    yield
    logger.info("Backend leáll.")


app = FastAPI(
    title="Soro.hu API",
    version="1.0.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routerek ──────────────────────────────────────────────────────────────────
try:
    from app.api.v1 import auth, articles, keywords, webhooks, account
    app.include_router(auth.router,     prefix="/v1/auth",     tags=["Auth"])
    app.include_router(articles.router, prefix="/v1/articles", tags=["Articles"])
    app.include_router(keywords.router, prefix="/v1/keywords", tags=["Keywords"])
    app.include_router(webhooks.router, prefix="/v1/webhooks", tags=["Webhooks"])
    app.include_router(account.router,  prefix="/v1/account",  tags=["Account"])
    logger.info("Összes router betöltve.")
except Exception as e:
    logger.error(f"Router betöltési hiba: {e}")
    raise


# ── Health – ezeket mindig válaszolja, DB nélkül is ──────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}

@app.get("/")
async def root():
    return {"service": "Soro.hu API", "status": "ok"}

@app.get("/v1/ping")
async def ping():
    return {"message": "Soro.hu API működik", "version": "1.0.0"}
