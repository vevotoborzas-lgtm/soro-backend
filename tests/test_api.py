"""
Soro.hu Backend – Alap tesztek
Futtatás: pytest tests/ -v
"""
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import init_db, engine, Base


@pytest_asyncio.fixture(scope="function")
async def client():
    # Test DB inicializálás
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as c:
        yield c

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Health check ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ping(client):
    r = await client.get("/v1/ping")
    assert r.status_code == 200
    assert r.json()["message"] == "Soro.hu API működik"


# ── Regisztráció ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_register(client):
    r = await client.post("/v1/auth/register", json={
        "email": "teszt@soro.hu",
        "password": "Teszt1234!",
        "first_name": "Teszt",
        "last_name": "Felhasználó",
    })
    assert r.status_code == 201
    data = r.json()
    assert "access_token" in data
    assert data["plan"] == "trial"
    assert data["articles_remaining"] == 5


@pytest.mark.asyncio
async def test_register_duplicate_email(client):
    payload = {"email": "dupla@soro.hu", "password": "Teszt1234!"}
    await client.post("/v1/auth/register", json=payload)
    r = await client.post("/v1/auth/register", json=payload)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_register_weak_password(client):
    r = await client.post("/v1/auth/register", json={
        "email": "gyenge@soro.hu",
        "password": "123",
    })
    assert r.status_code == 422


# ── Bejelentkezés ──────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_login(client):
    await client.post("/v1/auth/register", json={
        "email": "login@soro.hu", "password": "Teszt1234!"
    })
    r = await client.post("/v1/auth/login", json={
        "email": "login@soro.hu", "password": "Teszt1234!"
    })
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    await client.post("/v1/auth/register", json={
        "email": "rossz@soro.hu", "password": "Teszt1234!"
    })
    r = await client.post("/v1/auth/login", json={
        "email": "rossz@soro.hu", "password": "RosszJelszo"
    })
    assert r.status_code == 401


# ── Védett végpontok ──────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_account_requires_auth(client):
    r = await client.get("/v1/account")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_account_with_token(client):
    reg = await client.post("/v1/auth/register", json={
        "email": "fiok@soro.hu", "password": "Teszt1234!",
        "first_name": "Teszt", "last_name": "User"
    })
    token = reg.json()["access_token"]

    r = await client.get("/v1/account", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "fiok@soro.hu"
    assert data["plan"] == "trial"


# ── API kulcsok ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_api_key_create_and_list(client):
    reg = await client.post("/v1/auth/register", json={
        "email": "apikulcs@soro.hu", "password": "Teszt1234!"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Létrehozás
    r = await client.post("/v1/auth/keys", json={"name": "WP Plugin"}, headers=headers)
    assert r.status_code == 201
    key_data = r.json()
    assert key_data["key"].startswith("sk-soro-")

    # Lista
    r = await client.get("/v1/auth/keys", headers=headers)
    assert r.status_code == 200
    # 2 kulcs: az automatikus + az új
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_api_key_auth(client):
    """API kulccsal is lehet authentikálni."""
    reg = await client.post("/v1/auth/register", json={
        "email": "apikeyauth@soro.hu", "password": "Teszt1234!"
    })
    token = reg.json()["access_token"]
    headers_jwt = {"Authorization": f"Bearer {token}"}

    # Új API kulcs létrehozása
    r = await client.post("/v1/auth/keys", json={"name": "Test"}, headers=headers_jwt)
    api_key = r.json()["key"]

    # API kulccsal kérés
    r = await client.get("/v1/account", headers={"Authorization": f"Bearer {api_key}"})
    assert r.status_code == 200


# ── Account stats ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_account_stats(client):
    reg = await client.post("/v1/auth/register", json={
        "email": "stats@soro.hu", "password": "Teszt1234!"
    })
    token = reg.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = await client.get("/v1/account/stats", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert "total_articles" in data
    assert "articles_remaining" in data
    assert data["plan"] == "trial"
