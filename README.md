# Soro.hu Backend API

Python + FastAPI alapú backend a Soro.hu AI SEO autopilot platformhoz.

## Architektúra

```
soro-backend/
├── app/
│   ├── main.py                    # FastAPI app, routerek, CORS
│   ├── core/
│   │   ├── config.py              # Beállítások (.env)
│   │   ├── database.py            # SQLAlchemy async
│   │   └── security.py            # JWT, API kulcs, auth
│   ├── models/
│   │   ├── user.py                # User model
│   │   ├── article.py             # Article + APIKey model
│   │   └── api_key.py             # Re-export
│   ├── services/
│   │   └── ai_service.py          # Anthropic API integráció
│   └── api/v1/
│       ├── auth.py                # Regisztráció, login, API kulcsok
│       ├── articles.py            # Cikk generálás, lista, publikálás
│       ├── keywords.py            # Kulcsszókutatás
│       ├── webhooks.py            # WordPress publish webhook
│       └── account.py             # Fiók, stats
├── requirements.txt
├── .env.example
├── Procfile                       # Heroku / Railway
├── railway.toml                   # Railway deploy config
└── render.yaml                    # Render deploy config
```

## API Endpointok

| Method | Endpoint | Leírás |
|--------|----------|--------|
| GET | /v1/ping | Health check |
| POST | /v1/auth/register | Regisztráció |
| POST | /v1/auth/login | Bejelentkezés |
| GET | /v1/auth/keys | API kulcsok listája |
| POST | /v1/auth/keys | Új API kulcs |
| DELETE | /v1/auth/keys/{id} | API kulcs visszavonása |
| POST | /v1/auth/change-password | Jelszó módosítás |
| POST | /v1/articles/generate | AI cikk generálás |
| GET | /v1/articles | Cikk lista |
| GET | /v1/articles/{id} | Egy cikk adatai |
| DELETE | /v1/articles/{id} | Cikk törlése |
| GET | /v1/articles/scheduled | Ütemezett cikkek (WP plugin) |
| POST | /v1/articles/{id}/published | Publikálás visszaigazolás |
| POST | /v1/keywords | Kulcsszó javaslatok |
| GET | /v1/account | Fiók adatok |
| PATCH | /v1/account | Fiók módosítás |
| GET | /v1/account/stats | Statisztikák |
| POST | /v1/webhooks/publish-confirm | WordPress webhook |

## Helyi fejlesztés

```bash
# 1. Repo klónozás
git clone https://github.com/sajatrepo/soro-backend
cd soro-backend

# 2. Virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Függőségek
pip install -r requirements.txt

# 4. Env fájl
cp .env.example .env
# Szerkeszd a .env fájlt – különösen az ANTHROPIC_API_KEY-t!

# 5. Indítás
uvicorn app.main:app --reload --port 8000

# API docs: http://localhost:8000/docs
```

## Deploy – Railway (ajánlott)

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub
2. Kapcsold össze a GitHub repót
3. Add meg a környezeti változókat:
   - `ANTHROPIC_API_KEY` = Anthropic kulcsod
   - `JWT_SECRET` = véletlenszerű erős string
   - `SECRET_KEY` = véletlenszerű erős string
   - `ENVIRONMENT` = production
4. Railway automatikusan deployol minden push után
5. Egyedi domain: Settings → Domains → Generate Domain

## Deploy – Render

1. [render.com](https://render.com) → New → Web Service
2. GitHub repo csatlakoztatása
3. A `render.yaml` automatikusan konfigurálja
4. Environment Variables-ben add meg az `ANTHROPIC_API_KEY`-t
5. Create Web Service

## WordPress Plugin csatlakoztatása

A plugin a `soro-hu.php` fájlban az `SORO_API_BASE` konstanst használja.
Módosítsd az éles URL-re:

```php
define( 'SORO_API_BASE', 'https://soro-hu-api.railway.app/v1' );
```

Vagy a plugin Beállítások oldalán állítsd be az API kulcsot –
a plugin automatikusan a `https://api.soro.hu/v1` végpontot használja.

## Autentikáció

Minden védett endpoint `Authorization: Bearer <token>` headert vár.

**JWT token** (dashboard login után):
```
Authorization: Bearer eyJhbGciOiJIUzI1NiJ9...
```

**API kulcs** (WordPress plugin):
```
Authorization: Bearer sk-soro-xxxxxxxxxxxx
```

## Csomagok és limitek

| Csomag | Cikkek/hó | Ár |
|--------|-----------|-----|
| trial  | 5         | ingyenes (14 nap) |
| starter| 10        | €19/hó |
| pro    | 50        | €49/hó |
| agency | korlátlan | €149/hó |

## Production checklist

- [ ] `ENVIRONMENT=production` beállítva
- [ ] Erős `JWT_SECRET` és `SECRET_KEY`
- [ ] `ANTHROPIC_API_KEY` beállítva
- [ ] `ALLOWED_ORIGINS` csak a valódi domaineket tartalmazza
- [ ] PostgreSQL adatbázis (SQLite nem production-ready)
- [ ] HTTPS-t enforced a deploy platformon
- [ ] Swagger docs letiltva (`docs_url=None`)
