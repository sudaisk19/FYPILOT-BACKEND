# FYPilot Backend

A **Layered + Repository**–pattern FastAPI backend with real-time LLM support, database migrations, automated testing, and CI/CD. This README explains what lives in each folder, walks through a User CRUD example, and shows how to write unit tests.

---

## 🚀 Project Overview

- **REST endpoints** under `/v1/…`  
- **WebSocket** endpoint at `/ws/llm` for streaming LLM responses  
- **Layered architecture**: API → Services → Repositories → DB  
- **In-memory stubs** for fast prototyping, easily swapped for SQLAlchemy or Supabase implementations  
- **Alembic** for schema migrations  
- **pytest/pytest-asyncio** for unit & integration tests  
- **GitHub Actions** for CI/CD; production deploy targets **DigitalOcean** (Droplet + Docker). See `docs/deployment/digitalocean.md`.

---

## 📂 Folder Structure ( with demo files )


fastapi-backend/
├── app/
│   ├── api/
│   │   ├── health.py
│   │   └── users.py
│   ├── services/
│   │   └── user_service.py
│   ├── repositories/
│   │   └── user_repo.py
│   ├── models/
│   │   └── user.py
│   ├── schemas/
│   │   └── user_schema.py
│   ├── core/
│   │   ├── config.py
│   │   └── ai_clients.py
│   ├── auth/
│   │   └── supabase_auth.py
│   ├── db.py
│   └── main.py
│
├── tests/
│   ├── unit/
│   │   ├── test_health.py
│   │   └── test_users.py
│   └── integration/
│       └── test_user_integration.py
│
├── alembic/
│   └── versions/
│       └── 20250705_create_initial_tables.py
├── alembic.ini
├── .github/
│   └── workflows/
│       └── backend-ci.yml
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md


##CONTROLLERS AND ROUTERS 
app/api/
|
|--------|HTTP
│   
│       ├── health.py
│       ├── users.py
│       ├── proposals.py
│       └── router.py         # aggregates & tags all v1 HTTP routers
└── websocket/
    └── v1/
        ├── llm.py
        └── router.py         # aggregates all WS routers


##FURTHER ABOUT UNIT TESTING 

tests/
└── unit/
    ├── api/                 # tests for app/api/*
    │   ├── test_health.py   # GET /health returns 200 + {"status":"ok"}
    │   └── test_users.py    # POST/GET /v1/users endpoints
    │
    ├── services/            # tests for app/services/*
    │   └── test_user_service.py
    │
    ├── repositories/        # tests for app/repositories/*
    │   └── test_user_repo.py
    │
    └── core/                # tests for app/core/*
        └── test_config.py   # loads .env into settings correctly


## SETUP AFTER CLONING

# 1️⃣ Create the venv
python -m venv .venv

# 2️⃣ Activate it
.\.venv\Scripts\Activate.ps1

# 3️⃣ Install all pinned deps
pip install --upgrade pip
pip install -r requirements.txt

## run command 
uvicorn app.main:app --reload