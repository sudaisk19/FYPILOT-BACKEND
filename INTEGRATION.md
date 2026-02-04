# 🤖 FYPilot AI Recommender Service

> AI-powered supervisor recommendation service using FAISS vector search and sentence transformers.

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Local Development Setup](#local-development-setup)
4. [API Reference](#api-reference)
5. [Backend Integration Guide](#backend-integration-guide)
6. [Docker Deployment](#docker-deployment)
7. [DigitalOcean Droplet Deployment](#digitalocean-droplet-deployment)
8. [CI/CD Pipeline](#cicd-pipeline)
9. [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

The FYPilot AI Recommender Service provides intelligent supervisor matching for Final Year Project (FYP) groups. It analyzes:

- **Project domain & description**
- **Industry focus**
- **Project type** (research, product, etc.)
- **Student skills & experience**

And returns ranked supervisor recommendations with match scores and explanations.

### Tech Stack

| Component | Technology |
|-----------|------------|
| Framework | FastAPI |
| Vector Search | FAISS (Facebook AI Similarity Search) |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Database | Supabase (PostgreSQL) |
| Containerization | Docker |
| CI/CD | GitHub Actions |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Backend (Main)                    │
│                  (Your existing backend)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP Request
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              AI Recommender Service (This Service)          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   FastAPI   │──│ Recommender │──│  FAISS Vector Store │  │
│  │   Routes    │  │   Engine    │  │  (supervisors.index)│  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│         │                                    ▲               │
│         ▼                                    │               │
│  ┌─────────────────────────────────────────────┐            │
│  │         Sentence Transformer Model          │            │
│  │       (all-MiniLM-L6-v2 embeddings)        │            │
│  └─────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Supabase Database                         │
│              (Supervisor & Student data)                     │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Local Development Setup

### Prerequisites

- Python 3.12+
- pip or Poetry
- Supabase account with project set up

### Step 1: Clone & Setup Environment

```bash
cd ~/projects/Recommender

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 2: Configure Environment Variables

```bash
# Copy example env file
cp .env.example .env

# Edit with your Supabase credentials
nano .env
```

**Required `.env` variables:**

```env
# App Settings
DEBUG=false

# Supabase Database (Direct connection)
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# Supabase SDK
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-key
```

### Step 3: Run the Service

```bash
# Using the root main.py (development)
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Step 4: Verify It's Running

```bash
# Health check
curl http://localhost:8000/health

# Expected response:
# {"status": "healthy", "service": "fypilot-ai-service"}
```

**Swagger Docs:** http://localhost:8000/docs

---

## 📡 API Reference

### Base URL

| Environment | URL |
|-------------|-----|
| Local | `http://localhost:8000` |
| Docker | `http://localhost:8000` |
| Production | `https://your-droplet-ip:8000` |

---

### 1. Health Check

```http
GET /health
```

**Response:**
```json
{
    "status": "healthy",
    "service": "fypilot-ai-service"
}
```

---

### 2. Get Supervisor Recommendations

```http
POST /recommend
Content-Type: application/json
```

**Request Body:**
```json
{
    "project_domain": "Machine Learning",
    "industry": "Healthcare",
    "project_type": "research",
    "description": "AI-powered disease prediction using patient medical history",
    "members": [
        {
            "skills": {
                "Python": "advanced",
                "Machine Learning": "intermediate",
                "Data Analysis": "advanced"
            },
            "cgpa": 3.5,
            "past_projects": ["Sentiment Analysis Tool", "Data Visualization Dashboard"]
        },
        {
            "skills": {
                "Python": "intermediate",
                "Deep Learning": "beginner",
                "SQL": "advanced"
            },
            "cgpa": 3.2,
            "past_projects": ["Database Management System"]
        }
    ]
}
```

**Response:**
```json
{
    "results": [
        {
            "supervisor_id": "sup_123",
            "name": "Dr. Ahmed Khan",
            "department": "Computer Science",
            "score": 0.89,
            "reason": "Strong match: Expertise in ML and Healthcare AI, research-focused",
            "domains": ["Machine Learning", "Healthcare AI"],
            "requirements": ["Python proficiency", "Research experience"],
            "project_type": ["research", "product"],
            "user_id": "user_abc",
            "profile_avatar": "https://..."
        },
        {
            "supervisor_id": "sup_456",
            "name": "Dr. Sara Ali",
            "department": "Data Science",
            "score": 0.82,
            "reason": "Good fit: Data Science background aligns with project needs",
            "domains": ["Data Science", "Predictive Analytics"],
            "requirements": ["Strong statistics background"],
            "project_type": ["research"],
            "user_id": "user_def",
            "profile_avatar": "https://..."
        }
    ]
}
```

---

### 3. Refresh Supervisor Embeddings (Webhook)

```http
POST /refresh-supervisors
X-Webhook-Secret: your-webhook-secret
```

**Use Case:** Called by Supabase webhook when supervisor data is updated.

**Response:**
```json
{
    "status": "ok",
    "embedded_supervisors": 42
}
```

---

## 🔗 Backend Integration Guide

### Option A: HTTP Client (Recommended)

Add to your FastAPI backend's service layer:

```python
# app/services/ai_recommender.py

import httpx
from typing import List, Dict, Any
from pydantic import BaseModel

class AIRecommenderService:
    """Client for AI Recommender microservice"""
    
    def __init__(self):
        # Local development
        self.base_url = "http://localhost:8000"
        # Production (update after deployment)
        # self.base_url = "http://ai-recommender-service:8000"  # Docker network
        # self.base_url = "http://your-droplet-ip:8000"  # Direct IP
        
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def get_recommendations(
        self,
        project_domain: str,
        description: str,
        members: List[Dict],
        industry: str = None,
        project_type: str = None
    ) -> Dict[str, Any]:
        """
        Get supervisor recommendations for a group
        """
        payload = {
            "project_domain": project_domain,
            "description": description,
            "members": members,
            "industry": industry,
            "project_type": project_type
        }
        
        response = await self.client.post(
            f"{self.base_url}/recommend",
            json=payload
        )
        response.raise_for_status()
        return response.json()
    
    async def health_check(self) -> bool:
        """Check if AI service is healthy"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            return response.status_code == 200
        except httpx.RequestError:
            return False
    
    async def close(self):
        await self.client.aclose()


# Singleton instance
ai_recommender = AIRecommenderService()
```

### Usage in Your Router

```python
# app/api/v1/recommendations.py

from fastapi import APIRouter, HTTPException, Depends
from app.services.ai_recommender import ai_recommender
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse

router = APIRouter()

@router.post("/groups/{group_id}/recommendations", response_model=RecommendationResponse)
async def get_group_recommendations(
    group_id: str,
    request: RecommendationRequest,
    # Add your auth dependencies here
):
    """
    Get supervisor recommendations for a group
    """
    # Check AI service health
    if not await ai_recommender.health_check():
        raise HTTPException(
            status_code=503,
            detail="AI Recommender service is unavailable"
        )
    
    try:
        # Format members for AI service
        members = [
            {
                "skills": member.skills,
                "cgpa": member.cgpa,
                "past_projects": member.past_projects
            }
            for member in request.members
        ]
        
        # Call AI service
        result = await ai_recommender.get_recommendations(
            project_domain=request.project_domain,
            description=request.description,
            members=members,
            industry=request.industry,
            project_type=request.project_type
        )
        
        return result
        
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=502,
            detail=f"AI service error: {str(e)}"
        )
```

### Option B: Environment-based URL Configuration

```python
# app/core/config.py (in your main backend)

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ... your existing settings ...
    
    # AI Recommender Service
    AI_RECOMMENDER_URL: str = "http://localhost:8000"
    
    class Config:
        env_file = ".env"

settings = Settings()
```

Then in your `.env`:
```env
# Development
AI_RECOMMENDER_URL=http://localhost:8000

# Production (after deployment)
# AI_RECOMMENDER_URL=http://your-droplet-ip:8000
```

---

## 🐳 Docker Deployment

### Local Docker Testing

```bash
cd ~/projects/Recommender

# Build and run
docker compose up --build

# Run in background
docker compose up -d --build

# View logs
docker compose logs -f ai-service

# Stop
docker compose down
```

### Verify Docker Container

```bash
# Check container is running
docker ps

# Test health endpoint
curl http://localhost:8000/health

# Test recommendation endpoint
curl -X POST http://localhost:8000/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "project_domain": "Web Development",
    "description": "E-commerce platform",
    "members": [{"skills": {"JavaScript": "advanced"}, "cgpa": 3.0}]
  }'
```

---

## 🌊 DigitalOcean Droplet Deployment

### Prerequisites

1. **DigitalOcean Droplet** (Ubuntu 22.04+ recommended)
2. **Docker & Docker Compose** installed on droplet
3. **GitHub repository secrets** configured

### Step 1: Prepare Your Droplet

SSH into your droplet and run:

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo apt install docker-compose-plugin -y

# Create project directory
mkdir -p ~/recommender
cd ~/recommender
```

### Step 2: Upload Configuration Files

Upload these files to your droplet's `~/recommender` directory:

1. `docker-compose.prod.yml` (already created)
2. `.env` (with production credentials)

```bash
# Create .env on droplet
nano ~/recommender/.env
```

Add your production environment variables:
```env
DEBUG=false
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres
SUPABASE_URL=https://your-project-id.supabase.co
SUPABASE_KEY=your-supabase-anon-key
DOCKER_USERNAME=your-dockerhub-username
```

### Step 3: Configure GitHub Secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions**

Add these secrets:

| Secret Name | Value |
|-------------|-------|
| `DOCKER_USERNAME` | Your Docker Hub username |
| `DOCKER_PASSWORD` | Your Docker Hub password/token |
| `DROPLET_IP` | Your droplet's IP address |
| `DROPLET_USER` | SSH username (usually `root`) |
| `SSH_PRIVATE_KEY` | Your SSH private key (full content) |

### Step 4: First Manual Deployment

On your droplet:

```bash
cd ~/recommender

# Login to Docker Hub
docker login

# Pull and run
export DOCKER_USERNAME=your-username
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d

# Verify
docker ps
curl http://localhost:8000/health
```

### Step 5: Automatic Deployments

After the first manual setup, every push to `main` will:

1. ✅ Build Docker image
2. ✅ Push to Docker Hub
3. ✅ SSH to droplet
4. ✅ Pull new image
5. ✅ Restart container

---

## 🔄 CI/CD Pipeline

The GitHub Actions workflow (`.github/workflows/deploy.yml`) handles:

```
Push to main → Build Docker Image → Push to Hub → SSH Deploy
```

### Pipeline Status

Check your deployment status at:
`https://github.com/AzkaSahar/Recommender/actions`

### Manual Trigger

You can also manually trigger a deployment from the Actions tab.

---

## 🔧 Troubleshooting

### Common Issues

#### 1. Service not starting

```bash
# Check logs
docker compose logs -f ai-service

# Common fix: Check .env file exists and has correct values
cat .env
```

#### 2. FAISS index not loading

```bash
# Ensure supervisors.index and supervisors.json exist
ls -la supervisors.*

# If missing, restart service to regenerate from Supabase
docker compose restart ai-service
```

#### 3. Connection to Supabase failing

```bash
# Verify DATABASE_URL format
# Format: postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres

# Test connection
docker compose exec ai-service python -c "from db import test_connection; test_connection()"
```

#### 4. Health check failing

```bash
# Docker Compose v2 needs curl installed in container
# Already fixed in Dockerfile, rebuild if needed:
docker compose build --no-cache
docker compose up -d
```

#### 5. Port already in use

```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill the process or use a different port
docker compose down
# Edit docker-compose.yml to use different port, e.g., 8001:8000
```

---

## 📞 Integration Checklist

Before deploying to production:

- [ ] AI Recommender service running locally ✅
- [ ] Backend calling AI service successfully ✅
- [ ] `.env` configured with production Supabase credentials
- [ ] Docker image builds successfully
- [ ] Docker Hub account created and secrets added to GitHub
- [ ] DigitalOcean droplet provisioned
- [ ] SSH key added to GitHub secrets
- [ ] First manual deployment successful
- [ ] CI/CD pipeline tested with a push to `main`

---

## 📝 Quick Reference

| Task | Command |
|------|---------|
| Run locally | `uvicorn main:app --reload --port 8000` |
| Run with Docker | `docker compose up --build` |
| View logs | `docker compose logs -f` |
| Rebuild | `docker compose build --no-cache` |
| Stop | `docker compose down` |
| Deploy manually | `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d` |

---

**Created:** February 2026  
**Service:** FYPilot AI Recommender  
**Version:** 1.0.0
