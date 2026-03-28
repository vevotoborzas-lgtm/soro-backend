from sqlalchemy import String, Boolean, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone, timedelta
from app.core.database import Base
from app.core.config import settings
import uuid


class User(Base):
    __tablename__ = "users"

    id:              Mapped[str]            = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email:           Mapped[str]            = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str]            = mapped_column(String(255), nullable=False)
    first_name:      Mapped[str]            = mapped_column(String(100), default="")
    last_name:       Mapped[str]            = mapped_column(String(100), default="")
    website:         Mapped[str]            = mapped_column(String(255), default="")
    is_active:       Mapped[bool]           = mapped_column(Boolean, default=True)
    is_verified:     Mapped[bool]           = mapped_column(Boolean, default=False)

    # ── Előfizetés ────────────────────────────────────────────────────────────
    plan:            Mapped[str]            = mapped_column(String(20), default="trial")
    plan_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trial_ends_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Cikk kvóta ────────────────────────────────────────────────────────────
    articles_used_this_month: Mapped[int]   = mapped_column(Integer, default=0)
    quota_reset_at:           Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Meta ──────────────────────────────────────────────────────────────────
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login:  Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Kapcsolatok ────────────────────────────────────────────────────────────
    articles: Mapped[list["Article"]] = relationship("Article", back_populates="user", cascade="all, delete-orphan")
    api_keys: Mapped[list["APIKey"]]  = relationship("APIKey",  back_populates="user", cascade="all, delete-orphan")

    @property
    def display_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or self.email

    @property
    def article_limit(self) -> int:
        return settings.PLAN_LIMITS.get(self.plan, settings.TRIAL_ARTICLE_LIMIT)

    @property
    def articles_remaining(self) -> int:
        return max(0, self.article_limit - self.articles_used_this_month)

    def set_trial(self):
        self.plan = "trial"
        self.trial_ends_at = datetime.now(timezone.utc) + timedelta(days=settings.TRIAL_DAYS)

    def can_generate_article(self) -> bool:
        return self.articles_remaining > 0
