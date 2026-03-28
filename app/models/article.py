from sqlalchemy import String, Boolean, DateTime, Integer, Text, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
from app.core.database import Base
import uuid


class Article(Base):
    __tablename__ = "articles"

    id:              Mapped[str]  = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:         Mapped[str]  = mapped_column(String(36), ForeignKey("users.id"), index=True)

    # ── Tartalom ──────────────────────────────────────────────────────────────
    title:           Mapped[str]       = mapped_column(String(500), default="")
    content:         Mapped[str]       = mapped_column(Text, default="")
    excerpt:         Mapped[str]       = mapped_column(Text, default="")
    meta_title:      Mapped[str]       = mapped_column(String(200), default="")
    meta_description:Mapped[str]       = mapped_column(String(300), default="")
    focus_keyword:   Mapped[str]       = mapped_column(String(200), default="")
    tags:            Mapped[str]       = mapped_column(String(500), default="")  # JSON lista

    # ── Minőség ───────────────────────────────────────────────────────────────
    seo_score:       Mapped[float]     = mapped_column(Float, default=0.0)
    word_count:      Mapped[int]       = mapped_column(Integer, default=0)
    language:        Mapped[str]       = mapped_column(String(10), default="hu")

    # ── Státusz ───────────────────────────────────────────────────────────────
    status:          Mapped[str]       = mapped_column(String(20), default="draft")
    # draft | scheduled | published | failed

    # ── Publikálás ────────────────────────────────────────────────────────────
    scheduled_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    wp_post_id:      Mapped[int | None]      = mapped_column(Integer, nullable=True)
    wp_post_url:     Mapped[str | None]      = mapped_column(String(500), nullable=True)
    target_site:     Mapped[str | None]      = mapped_column(String(255), nullable=True)

    # ── Kép ───────────────────────────────────────────────────────────────────
    image_url:       Mapped[str | None] = mapped_column(String(500), nullable=True)

    # ── Meta ──────────────────────────────────────────────────────────────────
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="articles")


# ─────────────────────────────────────────────────────────────────────────────

from app.core.database import Base as _Base  # noqa – újra importál hogy ne körkörösen

class APIKey(_Base):
    __tablename__ = "api_keys"

    id:          Mapped[str]  = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id:     Mapped[str]  = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name:        Mapped[str]  = mapped_column(String(100), default="Alapértelmezett kulcs")
    key_hash:    Mapped[str]  = mapped_column(String(64), unique=True, index=True)
    key_prefix:  Mapped[str]  = mapped_column(String(20), default="")   # első 12 karakter előnézet
    is_active:   Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at:Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship("User", back_populates="api_keys")
