from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets
import hashlib

from app.core.config import settings
from app.core.database import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="Authorization", auto_error=False)


# ── Jelszó ───────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(user_id: str, expires_delta: Optional[timedelta] = None) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "access"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

def decode_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        return None


# ── API kulcs generálás ───────────────────────────────────────────────────────
def generate_api_key() -> tuple[str, str]:
    """Visszaad: (plain_key, hashed_key)"""
    raw = settings.API_KEY_PREFIX + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed

def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


# ── Auth függőségek ───────────────────────────────────────────────────────────
async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    from app.models.user import User

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentikáció szükséges")

    token = credentials.credentials

    # JWT token
    if not token.startswith(settings.API_KEY_PREFIX):
        user_id = decode_token(token)
        if not user_id:
            raise HTTPException(status_code=401, detail="Érvénytelen token")
        user = await db.get(User, user_id)
        if not user or not user.is_active:
            raise HTTPException(status_code=401, detail="Felhasználó nem található")
        return user

    # API kulcs (Bearer sk-soro-...)
    return await get_user_by_api_key(token, db)


async def get_user_by_api_key(raw_key: str, db: AsyncSession):
    from app.models.api_key import APIKey
    from app.models.user import User

    hashed = hash_api_key(raw_key)
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == hashed, APIKey.is_active == True)
    )
    api_key_obj = result.scalar_one_or_none()

    if not api_key_obj:
        raise HTTPException(status_code=401, detail="Érvénytelen API kulcs")

    user = await db.get(User, api_key_obj.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Felhasználó nem aktív")

    # Utolsó használat frissítése
    from datetime import datetime, timezone
    api_key_obj.last_used_at = datetime.now(timezone.utc)
    await db.commit()

    return user


async def require_active_subscription(
    current_user=Depends(get_current_user),
):
    """Ellenőrzi, hogy van-e aktív előfizetés vagy trial."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    if current_user.plan == "trial":
        if current_user.trial_ends_at and current_user.trial_ends_at < now:
            raise HTTPException(
                status_code=402,
                detail="A próbaidőszak lejárt. Válassz előfizetési csomagot."
            )
    elif current_user.plan not in ("starter", "pro", "agency"):
        raise HTTPException(status_code=402, detail="Nincs aktív előfizetés")

    return current_user
