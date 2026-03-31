import logging
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

logger.info("main.py betöltés kezdete...")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

logger.info("FastAPI importálva")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("App indul...")
    try:
        from app.core.database import init_db
        await init_db()
        logger.info("DB kész")
    except Exception as e:
        logger.error(f"DB hiba: {e}")
    yield

app = FastAPI(title="Soro.hu API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("Routerek betöltése...")

try:
    from app.api.v1 import auth
    app.include_router(auth.router, prefix="/v1/auth", tags=["Auth"])
    logger.info("auth router OK")
except Exception as e:
    logger.error(f"auth router hiba: {e}")

try:
    from app.api.v1 import articles
    app.include_router(articles.router, prefix="/v1/articles", tags=["Articles"])
    logger.info("articles router OK")
except Exception as e:
    logger.error(f"articles router hiba: {e}")

try:
    from app.api.v1 import keywords
    app.include_router(keywords.router, prefix="/v1/keywords", tags=["Keywords"])
    logger.info("keywords router OK")
except Exception as e:
    logger.error(f"keywords router hiba: {e}")

try:
    from app.api.v1 import webhooks
    app.include_router(webhooks.router, prefix="/v1/webhooks", tags=["Webhooks"])
    logger.info("webhooks router OK")
except Exception as e:
    logger.error(f"webhooks router hiba: {e}")

try:
    from app.api.v1 import account
    app.include_router(account.router, prefix="/v1/account", tags=["Account"])
    logger.info("account router OK")
except Exception as e:
    logger.error(f"account router hiba: {e}")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"service": "Soro.hu API", "status": "ok"}

@app.get("/v1/ping")
async def ping():
    return {"message": "ok"}

logger.info("App felépítve, indul a szerver...")
