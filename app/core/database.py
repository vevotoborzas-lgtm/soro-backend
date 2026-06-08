from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


settings = get_settings()
engine = create_async_engine(settings.database_url, future=True, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def ensure_sqlite_user_columns(conn: AsyncConnection) -> None:
    if conn.dialect.name != "sqlite":
        return
    res = await conn.execute(text("PRAGMA table_info(users)"))
    cols = {row[1] for row in res.all()}
    statements: list[str] = []
    if "subscription_status" not in cols:
        statements.append("ALTER TABLE users ADD COLUMN subscription_status VARCHAR(32) DEFAULT 'none'")
    if "stripe_customer_id" not in cols:
        statements.append("ALTER TABLE users ADD COLUMN stripe_customer_id VARCHAR(255)")
    if "stripe_subscription_id" not in cols:
        statements.append("ALTER TABLE users ADD COLUMN stripe_subscription_id VARCHAR(255)")
    if "articles_quota_month" not in cols:
        statements.append("ALTER TABLE users ADD COLUMN articles_quota_month VARCHAR(7) DEFAULT ''")
    for sql in statements:
        await conn.execute(text(sql))


async def ensure_postgres_user_columns(conn: AsyncConnection) -> None:
    if conn.dialect.name not in ("postgresql", "postgres"):
        return
    # Idempotent adds for existing DBs created before subscription/billing fields existed.
    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS subscription_status VARCHAR(32) DEFAULT 'none'",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_customer_id VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS stripe_subscription_id VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS articles_quota_month VARCHAR(7) DEFAULT ''",
    ]
    for sql in statements:
        await conn.execute(text(sql))


async def ensure_user_schema_patches(conn: AsyncConnection) -> None:
    await ensure_sqlite_user_columns(conn)
    await ensure_postgres_user_columns(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
