# 🤖 FYPilot AI Recommender & Jury Matching Service

> API-powered AI service using FAISS vector search, semantic similarity, and Sentence Transformers to provide intelligent pairings for both Supervisors and Juries.

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [What's New! 🚀](#whats-new-)
3. [Architecture](#architecture)
4. [Local Development & Testing Setup](#local-development--testing-setup)
5. [API Reference - Supervisor Matching](#api-reference---supervisor-matching)
6. [API Reference - Jury Matching](#api-reference---jury-matching)
7. [DigitalOcean Droplet Deployment](#digitalocean-droplet-deployment)
8. [Backend Integration Guide](#backend-integration-guide)
9. [Supabase Webhooks & Re-indexing](#supabase-webhooks--re-indexing)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

The **FYPilot AI Service** consolidates two major intelligent matching functions:
1. **Supervisor Recommender**: Recommends the best-fit supervisors for Final Year Project (FYP) teams.
2. **Jury Matching**: Dynamically groups available faculty into jury pairs, then greedily batches and assigns ALL projects evenly to them using semantic and domain analysis.

### Tech Stack
| Component        | Technology                                 |
| ---------------- | ------------------------------------------ |
| **Framework**    | FastAPI                                    |
| **Core AI**      | FAISS, `sentence-transformers/all-mpnet-base-v2` |
| **Testing**      | `pytest` with `TestClient` and `AsyncMock` |
| **Database**     | Supabase (PostgreSQL)                      |
| **Deployment**   | Docker, GitHub Actions, DigitalOcean       |

---

## 🚀 What's New!

Recent updates implemented across the entire service to modernize, stabilize, and verify deployments:
1. **Pytest Integration**: Created fully isolated testing environments (`tests/test_supervisor_matching.py` and `tests/test_jury_matching.py`) mocking FAISS background events via `unittest.mock.AsyncMock`. You can now run `pytest` directly to verify API schemas are unbroken!
2. **Modern `lifespan` Handlers**: FastAPI's deprecated `@app.on_event("startup")` mechanisms have been successfully replaced with standard async Python `@asynccontextmanager` lifespans for stable container startups.
3. **Robust Fallbacks**: AI assignments rely heavily on `.json` fallbacks and dynamic scoring limits to ensure safe matching constraints and limits.

---

## 🏗️ Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                    Your FYPilot Backend                      │
│                 (Node.js / Express / NestJS)                 │
└─┬──────────────────────────────────────────────────────────┬─┘
  │ 1. Fetch Supervisor     OR     2. Batch Admin Jury Match │
  ▼                                                          ▼
┌─────────────────────────────────────────────────────────────┐
│                 AI Recommender Service (Port 8001)           │
│                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌─────────────┐  │
│  │ FastAPI HTTP │────▶│  Service     │────▶│ FAISS (RAM) │  │
│  │   Routers    │     │ Scoring Logic│     │ .index files│  │
│  └──────────────┘     └──────────────┘     └─────────────┘  │
└────────────────┬────────────────────────────────────────────┘
                 │ Read/Write DB via Supabase
                 ▼
┌─────────────────────────────────────────────────────────────┐
│                      Supabase Database                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Local Development & Testing Setup

### 1. Requirements & Setup

- Python 3.12+ 
- Virtual environment correctly configured.

```bash
cd ~/projects/Recommender
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env # make sure to populate the secrets
```

### 2. Verify with Pytest (Sanity Check)

To ensure nothing is broken before you start the server:

```bash
venv/bin/python -m pytest tests/
```
*Outputs green ticks verifying that JSON inputs and API endpoints work properly mapping back to our models.*

### 3. Run the Server

```bash
uvicorn app.main:app --reload --port 8001
```

---

## 📡 API Reference - Supervisor Matching

**Base URL**: `http://localhost:8001/api/v1/supervisor`

### 1. `POST /recommend`
Request recommendations for a group.

**Request Payload:**
```json
{
    "project_domain": "Machine Learning",
    "industry": "Healthcare",
    "project_type": "research",
    "description": "AI-powered disease prediction",
    "members": [
        { "skills": { "Python": "advanced" }, "cgpa": 3.5, "past_projects": [] }
    ]
}
```

**Response Payload:**
Returns an array of supervisors (`results[0].supervisor_id`, `.score`, `.reason`, `.profile_avatar`, etc.)

---

## 🎓 API Reference - Jury Matching

**Base URL**: `http://localhost:8001/api/v1/jury`

*How it works*: (1) Generates jury pairs dynamically `->` (2) Re-indexes project embeddings `->` (3) Batches every project into those pairs (ignoring actual native supervisors).

### 1. `POST /generate-pairs`
Generates optimal pairings out of currently available `is_jury=true` faculty.
### 2. `POST /batch`
Returns AI recommendations matching ALL projects concurrently.
### 3. `POST /reindex`
Background task triggering deep `.index` and `.json` rebuilds from Supabase. (Called by Webhooks).

---

## 🌊 DigitalOcean Droplet Deployment

Deployment is natively automated via GitHub Actions (`.github/workflows/deploy.yml`), publishing to Docker Hub and applying via ssh to the Droplet pulling `docker-compose.prod.yml`.

### Deployment Sanity Check

**⚠️ IMPORTANT NOTE:** To properly persist `FAISS` indexes on Docker rebuilds, the production deployment in `docker-compose.prod.yml` relies on volume bindings.

1. **Verify your droplet `.env`**: Make sure your Droplet contains `.env` in `~/recommender/.env` including `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_KEY` and `DOCKER_USERNAME`.
2. **Volumes Alert**: `docker-compose.prod.yml` binds `ai_index_data:/app/index_data`. Since your data inherently builds to `/app/` root by default as configured in `app/core/config.py`, this requires your production settings or container config to be mindful. 
> To align this seamlessly across instances, the AI service now executes locally without dropping FAISS indexes simply by regenerating models via Webhooks whenever Droplets reboot. Re-indexing is heavily robust!

### Manual Trigger
Run these on your Droplet if GitHub Actions fails or you want a pure manual pull:
```bash
cd ~/recommender
export DOCKER_USERNAME=your-username
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## 🔗 Backend Integration Guide

Integrating into your backend (Express / NestJS) is a direct API call wrapper:

```typescript
import axios from 'axios';

const AI_API_URL = process.env.AI_SERVICE_URL || 'http://localhost:8001';

// 1. Getting Supervisor matches
const res_supervisors = await axios.post(`${AI_API_URL}/api/v1/supervisor/recommend`, { ...payload });

// 2. Getting Full Jury Pair Batches
const res_jury = await axios.post(`${AI_API_URL}/api/v1/jury/batch`);
```

---

## 🔔 Supabase Webhooks & Re-indexing

Your Supabase Dashboard manages syncing state using Webhooks POSTing to the AI Service directly:

1. **AI Re-Index (Projects)**
   * **Table**: `public.projects` (Insert, Update, Delete)
   * **URL**: `http://YOUR_DROPLET_IP:8001/api/v1/jury/reindex`
2. **Refresh Supervisors**
   * **Table**: `public.supervisors` (Insert, Update, Delete)
   * **URL**: `http://YOUR_DROPLET_IP:8001/api/v1/supervisor/refresh-supervisors` (requires `X-Webhook-Secret` matching `.env`).

---

## 🔧 Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| `FAISS index not found` | Booted Docker from scratch w/o building indexes | Call `/api/v1/jury/reindex` manually once! |
| Port clashes | Port 8000/8001 occupied natively | Run `sudo lsof -i :8001` and kill respective PID |
| Tests failing (`pytest`) | You're not in the `venv` | Ensure you run it via `venv/bin/pytest tests/` |
| GitHub CI Fails SSH | The keys configured are incomplete | Replace full contents into `SSH_PRIVATE_KEY` |

---
*Generated & maintained actively for the complete combined FYPilot Recommendation Suite matching architecture.*
