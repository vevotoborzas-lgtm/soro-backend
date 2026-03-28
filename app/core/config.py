from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Any
import secrets
import json
import os


class Settings(BaseSettings):
    APP_NAME:    str = "Soro.hu API"
    ENVIRONMENT: str = "development"
    SECRET_KEY:  str = secrets.token_urlsafe(32)
    DEBUG:       bool = False

    DATABASE_URL: str = "sqlite+aiosqlite:///./soro.db"

    JWT_SECRET:                  str = secrets.token_urlsafe(32)
    JWT_ALGORITHM:               str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    API_KEY_PREFIX:              str = "sk-soro-"

    # Nem kötelező induláshoz – hiányában az AI funkciók 503-at adnak
    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL:   str = "claude-sonnet-4-20250514"
    MAX_TOKENS:        int = 4096

    ALLOWED_ORIGINS: List[str] = ["*"]

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_origins(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [o.strip() for o in v.split(",") if o.strip()]
        return ["*"]

    PLAN_LIMITS: dict = {"starter": 10, "pro": 50, "agency": 999999}
    TRIAL_DAYS:          int = 14
    TRIAL_ARTICLE_LIMIT: int = 5

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore"
    }


settings = Settings()
