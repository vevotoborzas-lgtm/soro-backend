from functools import lru_cache
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    secret_key: str = "change-me"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    database_url: str = "sqlite+aiosqlite:///./soro.db"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5-20251001"
    allowed_origins: list[str] = Field(default_factory=lambda: ["https://soro.hu"])
    webhook_secret: str = "change-me"
    monthly_article_quota: int = 100
    # Csomagok: soro-hu-theme template-pricing.php (Starter 10, Pro 50, Agency gyakorlatilag korlátlan)
    quota_trial: int = 10
    quota_starter: int = 10
    quota_pro: int = 50
    quota_agency: int = 999_999
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_agency: str = ""
    billing_success_url: str = "https://soro.hu/dashboard?checkout=success"
    billing_cancel_url: str = "https://soro.hu/arazas?checkout=canceled"
    billing_portal_return_url: str = "https://soro.hu/dashboard"
    # Frontend page that reads ?token= and posts new password to /v1/auth/reset-password
    password_reset_base_url: str = "https://soro.hu/auth/reset-password"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "no-reply@soro.hu"
    smtp_from_name: str = "Soro.hu"
    smtp_use_tls: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
