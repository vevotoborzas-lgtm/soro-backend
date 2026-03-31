from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, field_validator
from datetime import datetime, timezone
import re

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, create_access_token,
    generate_api_key, get_current_user
)
from app.models.user import User
from app.models.article import APIKey

router = APIRouter()


def validate_email(email: str) -> str:
    """Egyszerű email validáció – nem igényel külső csomagot."""
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        raise ValueError('Érvénytelen e-mail cím')
    return email.lower().strip()


class RegisterRequest(BaseModel):
    email:      str
    password:   str
    first_name: str = ""
    last_name:  str = ""
    website:    str = ""
    plan:       str = "trial"

    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        return validate_email(v)

    @field_validator("password")
    @classmethod
    def check_password(cls, v):
        if len(v) < 8:
            raise ValueError("A jelszónak legalább 8 karakter hosszúnak kell lennie")
        return v

    @field_validator("plan")
    @classmethod
    def check_plan(cls, v):
        return v if v in ("trial","starter","pro","agency") else "trial"


class LoginRequest(BaseModel):
    email:    str
    password: str

    @field_validator("email")
    @classmethod
    def check_email(cls, v):
        return validate_email(v)


class TokenResponse(BaseModel):
    access_token:       str
    token_type:         str = "bearer"
    user_id:            str
    email:              str
    plan:               str
    articles_remaining: int


class APIKeyCreate(BaseModel):
    name: str = "Alapértelmezett kulcs"


class APIKeyResponse(BaseModel):
    id:           str
    name:         str
    key:          str | None = None
    key_prefix:   str
    created_at:   datetime
    last_used_at: datetime | None


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password:     str

    @field_validator("new_password")
    @classmethod
    def check_password(cls, v):
        if len(v) < 8:
            raise ValueError("A jelszónak legalább 8 karakter hosszúnak kell lennie")
        return v


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == req.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ez az e-mail cím már regisztrálva van")

    user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        first_name=req.first_name,
        last_name=req.last_name,
        website=req.website,
    )
    user.set_trial()
    db.add(user)
    await db.flush()

    plain_key, key_hash = generate_api_key()
    api_key = APIKey(
        user_id=user.id,
        name="Alapértelmezett kulcs",
        key_hash=key_hash,
        key_prefix=plain_key[:16] + "...",
    )
    db.add(api_key)
    await db.commit()
    await db.refresh(user)

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token, user_id=user.id,
        email=user.email, plan=user.plan,
        articles_remaining=user.articles_remaining,
    )


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Hibás e-mail cím vagy jelszó")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="A fiók le van tiltva")
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token, user_id=user.id,
        email=user.email, plan=user.plan,
        articles_remaining=user.articles_remaining,
    )


@router.get("/keys", response_model=list[APIKeyResponse])
async def list_api_keys(current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    result = await db.execute(
        select(APIKey).where(APIKey.user_id==current_user.id, APIKey.is_active==True)
        .order_by(APIKey.created_at.desc())
    )
    return [APIKeyResponse(id=k.id, name=k.name, key_prefix=k.key_prefix,
                           created_at=k.created_at, last_used_at=k.last_used_at)
            for k in result.scalars().all()]


@router.post("/keys", response_model=APIKeyResponse, status_code=201)
async def create_api_key(req: APIKeyCreate, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    plain_key, key_hash = generate_api_key()
    api_key = APIKey(user_id=current_user.id, name=req.name,
                     key_hash=key_hash, key_prefix=plain_key[:16]+"...")
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return APIKeyResponse(id=api_key.id, name=api_key.name, key=plain_key,
                          key_prefix=api_key.key_prefix, created_at=api_key.created_at, last_used_at=None)


@router.delete("/keys/{key_id}", status_code=204)
async def revoke_api_key(key_id: str, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    result = await db.execute(select(APIKey).where(APIKey.id==key_id, APIKey.user_id==current_user.id))
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise HTTPException(status_code=404, detail="API kulcs nem található")
    api_key.is_active = False
    await db.commit()


@router.post("/change-password")
async def change_password(req: PasswordChangeRequest, current_user=Depends(get_current_user), db: AsyncSession=Depends(get_db)):
    if not verify_password(req.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="A jelenlegi jelszó helytelen")
    current_user.hashed_password = hash_password(req.new_password)
    await db.commit()
    return {"message": "Jelszó sikeresen módosítva"}
