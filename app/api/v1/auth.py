import logging
import re
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    decode_access_token,
    decode_password_reset_token,
    generate_api_key,
    get_password_hash,
    hash_api_key,
    key_prefix,
    verify_password,
)
from app.models.user import APIKey, User
from app.services.email_service import send_password_reset_email


router = APIRouter(prefix="/v1/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)
EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
log = logging.getLogger("soro.auth")
settings = get_settings()


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=2, max_length=120)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class ForgotPasswordIn(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not EMAIL_REGEX.match(v):
            raise ValueError("Invalid email format")
        return v.lower().strip()


class ResetPasswordIn(BaseModel):
    token: str = Field(min_length=10, max_length=2048)
    new_password: str = Field(min_length=8, max_length=128)


class APIKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None = None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Authorization token")

    token = credentials.credentials.strip()
    if token.startswith("sk-soro-"):
        key_hash = hash_api_key(token)
        key_query = await db.execute(select(APIKey).where(APIKey.key_hash == key_hash, APIKey.is_active.is_(True)))
        api_key = key_query.scalar_one_or_none()
        if not api_key:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        user_query = await db.execute(select(User).where(User.id == api_key.user_id, User.is_active.is_(True)))
        user = user_query.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        api_key.last_used_at = datetime.now(timezone.utc)
        await db.commit()
        return user

    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid JWT token")
    query = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = query.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/register")
@limiter.limit("5/minute")
async def register(request: Request, payload: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == payload.email.lower().strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already exists")

    names = payload.name.strip().split(" ", 1)
    first_name = names[0]
    last_name = names[1] if len(names) > 1 else ""

    user = User(
        email=payload.email.lower().strip(),
        hashed_password=get_password_hash(payload.password),
        first_name=first_name,
        last_name=last_name,
    )
    db.add(user)
    await db.flush()

    raw_key = generate_api_key()
    user_key = APIKey(
        user_id=user.id,
        name="Default",
        key_hash=hash_api_key(raw_key),
        key_prefix=key_prefix(raw_key),
    )
    db.add(user_key)
    await db.commit()
    await db.refresh(user)

    return {"access_token": create_access_token(user.id), "token_type": "bearer", "api_key": raw_key}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, payload: LoginIn, db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(User).where(User.email == payload.email.lower().strip()))
    user = query.scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(user.id), "token_type": "bearer"}


@router.get("/keys", response_model=list[APIKeyOut])
async def list_keys(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(APIKey).where(APIKey.user_id == user.id).order_by(APIKey.created_at.desc()))
    return list(query.scalars().all())


class CreateKeyIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.post("/keys")
async def create_key(payload: CreateKeyIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    raw_key = generate_api_key()
    item = APIKey(
        user_id=user.id,
        name=payload.name.strip(),
        key_hash=hash_api_key(raw_key),
        key_prefix=key_prefix(raw_key),
    )
    db.add(item)
    await db.commit()
    return {"id": item.id, "name": item.name, "api_key": raw_key, "key_prefix": item.key_prefix}


@router.delete("/keys/{key_id}")
async def delete_key(key_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = await db.execute(select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user.id))
    item = query.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Key not found")
    item.is_active = False
    await db.commit()
    return {"ok": True}


@router.post("/change-password")
async def change_password(payload: ChangePasswordIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return {"ok": True}


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, payload: ForgotPasswordIn, db: AsyncSession = Depends(get_db)):
    """Request a password reset. Always returns the same message (no email enumeration)."""
    query = await db.execute(select(User).where(User.email == payload.email))
    user = query.scalar_one_or_none()
    if user and user.is_active:
        token = create_password_reset_token(user.id)
        sep = "&" if "?" in settings.password_reset_base_url else "?"
        link = f"{settings.password_reset_base_url}{sep}token={token}"
        sent = send_password_reset_email(settings, to_email=payload.email, reset_link=link)
        if not sent:
            log.warning("password reset requested but email was not sent email=%s", payload.email)
    return {"ok": True, "message": "If an account exists for this email, reset instructions have been sent."}


@router.post("/reset-password")
@limiter.limit("10/minute")
async def reset_password(request: Request, payload: ResetPasswordIn, db: AsyncSession = Depends(get_db)):
    user_id = decode_password_reset_token(payload.token.strip())
    if not user_id:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    query = await db.execute(select(User).where(User.id == user_id, User.is_active.is_(True)))
    user = query.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    return {"ok": True}
