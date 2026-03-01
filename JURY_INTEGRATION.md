# 🎓 Jury Matching Service — Integration Guide

> AI-powered jury assignment for FYP projects using FAISS vector search, semantic similarity, and domain expertise matching.

---

## 📑 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [API Reference](#api-reference)
4. [Backend Integration Guide](#backend-integration-guide)
5. [Supabase Webhooks Setup](#supabase-webhooks-setup)
6. [How the Algorithm Works](#how-the-algorithm-works)
7. [File-by-File Breakdown](#file-by-file-breakdown)
8. [Running the Service](#running-the-service)
9. [Troubleshooting](#troubleshooting)
10. [FAQ](#faq)

---

## 🎯 Overview

The Jury Matching Service recommends the **best-fit jury panel** for every FYP project in a single batch operation. It analyzes:

- **Project description & title** (Semantic understanding via AI)
- **Project domains** (e.g., "Artificial Intelligence", "Web Development")
- **Project industry** (e.g., "Healthcare", "Fintech")
- **Supervisor exclusion** (A project's own supervisor cannot be on its jury)

### What It Does NOT Consider

- ❌ Tech stack (e.g., React, Python) — Jury don't evaluate code quality
- ❌ Student skills — Jury evaluates the project, not the students

### Key Features

| Feature | Description |
|---------|-------------|
| **Batch Processing** | Matches ALL projects (~300) in one API call |
| **Smart Exclusion** | Automatically removes a project's own supervisor from jury candidates |
| **Weighted Scoring** | 60% Semantic + 30% Domain + 10% Industry |
| **Auto Re-indexing** | Triggered by Supabase webhooks when project data changes |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│            Your Backend (Node.js / NestJS)               │
│                                                         │
│  1. Admin clicks "Assign Jury"                          │
│  2. Backend calls POST /api/v1/jury/batch               │
│  3. Backend receives ranked jury list per project       │
│  4. Backend assigns top candidates (your logic)         │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP POST
                         ▼
┌─────────────────────────────────────────────────────────┐
│           AI Recommender Service (This Service)          │
│                                                         │
│  ┌──────────┐   ┌──────────────┐   ┌────────────────┐  │
│  │ Router   │──▶│   Service    │──▶│ FAISS Indexes  │  │
│  │ (2 APIs) │   │ (Algorithm)  │   │ jury.index     │  │
│  └──────────┘   └──────────────┘   │ projects.index │  │
│                                    └────────────────┘  │
└─────────────────────────┬───────────────────────────────┘
                          │ SQL Queries
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  Supabase Database                       │
│  Tables: projects, groups, project_domains, industries,  │
│          supervisors, supervisor_domains,                 │
│          supervisor_industries                            │
└─────────────────────────────────────────────────────────┘
```

### Data Flow (Step-by-Step)

```
1. REINDEX (First Time / On Data Change)
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │ fetch_jury.py │────▶│ utils.py     │────▶│ build_jury   │
   │ fetch_proj.py │     │ (clean text) │     │ _index.py    │
   └──────────────┘     └──────────────┘     └──────┬───────┘
                                                     │
                                              jury.index + projects.index

2. BATCH MATCH (On Admin Request)
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │ projects.index│────▶│ service.py   │────▶│ JSON Response│
   │ jury.index   │     │ (score+rank) │     │ per project  │
   └──────────────┘     └──────────────┘     └──────────────┘
```

---

## 📡 API Reference

### Base URL

| Environment | URL |
|-------------|-----|
| Local | `http://localhost:8001` |
| Production | `http://YOUR_DROPLET_IP:8001` |

> **Swagger Docs:** `http://localhost:8001/docs`

---

### 1. Batch Match (Core Endpoint)

```http
POST /api/v1/jury/batch
Content-Type: application/json
```

**Request Body:** None (uses pre-built indexes)

**Response:** `200 OK`

```json
[
  {
    "project_id": "0dce553b-d58f-4680-9b0d-4a56df633ed1",
    "title": "Smart Attendance using Vision",
    "matches": [
      {
        "jury_id": "6a1221f3-e73e-47d6-8a08-0bbcbe7fd6fc",
        "name": "Dr. Farah Siddiqui",
        "department": "Computer Science",
        "designation": "Associate Professor",
        "score": 47.5,
        "reason": "✓ Domain Expert"
      },
      {
        "jury_id": "29d09c99-49fe-4692-a32c-f72bb890319e",
        "name": "Mr Sameer Faisal",
        "department": "Artificial Intelligence",
        "designation": "Lecturer",
        "score": 46.6,
        "reason": "✓ Domain Expert"
      }
    ]
  },
  {
    "project_id": "abc123-...",
    "title": "E-Commerce Platform",
    "matches": [
      {
        "jury_id": "...",
        "name": "Dr. Web Expert",
        "department": "Software Engineering",
        "designation": "Professor",
        "score": 82.3,
        "reason": "✓ Domain Expert | Strong Topic Alignment (75%)"
      }
    ]
  }
]
```

#### Response Schema

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `string (UUID)` | The project's unique ID |
| `title` | `string` | The project name |
| `matches` | `List[JuryMatch]` | Ranked list of jury candidates (best first) |
| `matches[].jury_id` | `string (UUID)` | Supervisor's ID (use this to assign in your DB) |
| `matches[].name` | `string` | Supervisor's full name |
| `matches[].department` | `string` | Department name |
| `matches[].designation` | `string` | e.g., "Professor", "Associate Professor", "Lecturer" |
| `matches[].score` | `float` | Match score (0–100). Higher = better fit |
| `matches[].reason` | `string` | Human-readable explanation of why this match was made |

#### Score Meaning

| Score Range | Quality | Action |
|-------------|---------|--------|
| 70–100 | 🟢 Excellent | Auto-assign |
| 40–69 | 🟡 Good | Assign with confidence |
| 20–39 | 🟠 Moderate | Assign if no better option |
| 0–19 | 🔴 Weak | Flag for manual review |

#### Reason Tags

| Tag | Meaning |
|-----|---------|
| `✓ Domain Expert` | Supervisor has a matching domain (e.g., both have "AI") |
| `Strong Topic Alignment (X%)` | AI found high semantic similarity (>60%) |
| `Moderate Interest Match` | AI found moderate semantic similarity (40–60%) |
| `✓ Industry Context` | Supervisor works in the same industry |
| `General Competence` | No specific overlap, but closest available match |

---

### 2. Re-Index (Rebuild Everything)

```http
POST /api/v1/jury/reindex
Content-Type: application/json
```

**Request Body:** None

**Response:** `200 OK`

```json
{
  "status": "ok",
  "message": "Full re-indexing started in background."
}
```

> ⚠️ This runs in the **background**. It will take 10–30 seconds to complete.  
> After completion, the next `/batch` call will use the fresh data.

**When to call this:**
- When the admin triggers "Refresh Data" from the dashboard
- When Supabase webhook fires (project data changed)
- Before the first-ever `/batch` call

---

## 🔗 Backend Integration Guide

### Step 1: Add AI Service URL to Your Config

```typescript
// config.ts (your NestJS/Express backend)
export const AI_SERVICE_URL = process.env.AI_SERVICE_URL || 'http://localhost:8001';
```

### Step 2: Create the AI Client Service

```typescript
// services/ai-jury.service.ts

import axios from 'axios';

interface JuryMatch {
  jury_id: string;
  name: string;
  department: string;
  designation: string;
  score: number;
  reason: string;
}

interface BatchProjectMatch {
  project_id: string;
  title: string;
  matches: JuryMatch[];
}

export class AIJuryService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = process.env.AI_SERVICE_URL || 'http://localhost:8001';
  }

  /**
   * Step 1: Trigger re-indexing (call before batch match if data has changed)
   */
  async reindex(): Promise<void> {
    await axios.post(`${this.baseUrl}/api/v1/jury/reindex`);
    // Wait for background task to complete (optional, takes ~20s)
    await new Promise(resolve => setTimeout(resolve, 20000));
  }

  /**
   * Step 2: Get jury recommendations for ALL projects
   */
  async getBatchMatches(): Promise<BatchProjectMatch[]> {
    const response = await axios.post(`${this.baseUrl}/api/v1/jury/batch`);
    return response.data;
  }

  /**
   * Step 3: Your assignment logic
   * Takes AI recommendations and assigns jury members, handling conflicts.
   */
  async assignJury(): Promise<void> {
    // 1. Get AI Recommendations
    const recommendations = await this.getBatchMatches();

    // 2. Track assigned jury members (to avoid overloading one person)
    const juryLoadMap: Record<string, number> = {}; // jury_id -> count of assignments
    const MAX_ASSIGNMENTS_PER_JURY = 10; // Configurable limit

    // 3. Process each project
    for (const project of recommendations) {
      const assigned: string[] = [];

      for (const match of project.matches) {
        // Skip if this jury member is already overloaded
        const currentLoad = juryLoadMap[match.jury_id] || 0;
        if (currentLoad >= MAX_ASSIGNMENTS_PER_JURY) continue;

        // Assign this jury member
        assigned.push(match.jury_id);
        juryLoadMap[match.jury_id] = currentLoad + 1;

        // Stop after assigning 2 jury members per project
        if (assigned.length >= 2) break;
      }

      // 4. Save to your database
      // await this.db.updateProjectJury(project.project_id, assigned);
      console.log(`Project "${project.title}" → Jury: ${assigned.join(', ')}`);
    }
  }
}
```

### Step 3: Wire It to Your Admin Endpoint

```typescript
// controllers/admin.controller.ts

@Post('/admin/assign-jury')
async assignJury() {
  const aiService = new AIJuryService();

  // Step 1: Rebuild indexes with latest data
  await aiService.reindex();

  // Step 2: Get recommendations + assign
  await aiService.assignJury();

  return { message: 'Jury assignment complete' };
}
```

---

## 🔔 Supabase Webhooks Setup

You need **2 webhooks** (created via Supabase Dashboard):

### Webhook 1: Projects Table

| Setting | Value |
|---------|-------|
| **Name** | `AI Re-Index (Projects)` |
| **Table** | `public.projects` |
| **Events** | ✅ Insert, ✅ Update, ✅ Delete |
| **Type** | HTTP Request |
| **Method** | POST |
| **URL** | `http://YOUR_DROPLET_IP:8001/api/v1/jury/reindex` |

### Webhook 2: Project Domains Table

| Setting | Value |
|---------|-------|
| **Name** | `AI Re-Index (Domains)` |
| **Table** | `public.project_domains` |
| **Events** | ✅ Insert, ✅ Update, ✅ Delete |
| **Type** | HTTP Request |
| **Method** | POST |
| **URL** | `http://YOUR_DROPLET_IP:8001/api/v1/jury/reindex` |

> ⚠️ **Note:** The AI service must be publicly accessible for webhooks to reach it. Use your Droplet's public IP or domain.

---

## 🧠 How the Algorithm Works

### Scoring Formula

```
Final Score = (Semantic × 0.60) + (Domain × 0.30) + (Industry × 0.10)
```

| Component | Weight | How It Works |
|-----------|--------|--------------|
| **Semantic** | 60% | AI reads the project description and compares it to the supervisor's expertise profile. Uses SBERT (all-mpnet-base-v2) embeddings + FAISS cosine similarity. |
| **Domain** | 30% | Exact match check. If the supervisor has "Artificial Intelligence" in their domains and the project also has "Artificial Intelligence" → full 30 points. |
| **Industry** | 10% | Exact match check. If the supervisor works in "Healthcare" and the project's industry is "Healthcare" → full 10 points. |

### Exclusion Logic

- A project's **own supervisor** is automatically excluded from jury candidates.
- This uses the `supervisor_id` from the `groups` table.

### What Happens When No Expert Matches?

The system **always returns results**. If no domain/industry match exists, the AI falls back to pure semantic similarity. The `reason` field will show `"General Competence"` and the score will be low (< 20). Your backend should flag these for manual review.

---

## 📁 File-by-File Breakdown

### Study Order (Start Here → End Here)

| # | File | Purpose | Read Time |
|---|------|---------|-----------|
| 1 | `app/core/config.py` | Configuration: index paths, scoring weights, DB URL | 2 min |
| 2 | `app/services/jury_matching/schemas.py` | Data contracts: `JuryMatch`, `BatchProjectMatch`, `ProjectProfileRequest` | 3 min |
| 3 | `app/services/jury_matching/scripts/fetch_jury.py` | SQL: fetches all supervisors with domains, industries, designation | 5 min |
| 4 | `app/services/jury_matching/scripts/fetch_projects.py` | SQL: fetches all projects with domains, industry, supervisor_id | 5 min |
| 5 | `app/services/jury_matching/utils.py` | Text preparation: converts raw data into clean semantic strings | 3 min |
| 6 | `app/services/jury_matching/scripts/build_jury_index.py` | Indexer: text → embeddings → `jury.index` file | 5 min |
| 7 | `app/services/jury_matching/scripts/build_project_index.py` | Indexer: text → embeddings → `projects.index` file | 3 min |
| 8 | `app/services/jury_matching/store.py` | Memory loader: reads `jury.index` into RAM for fast search | 2 min |
| 9 | `app/services/jury_matching/service.py` | ⭐ **THE CORE**: `recommend_batch()` — scoring, ranking, exclusion | 10 min |
| 10 | `app/services/jury_matching/router.py` | API layer: `/batch` and `/reindex` endpoints | 2 min |

### Mental Model

```
fetch_jury.py + fetch_projects.py     ← Get raw data from DB
              ↓
          utils.py                    ← Clean it into readable text
              ↓
build_jury_index.py + build_project_index.py  ← Convert text → Vectors
              ↓
          store.py                    ← Load vectors into memory
              ↓
          service.py                  ← Score & Rank matches (THE BRAIN)
              ↓
          router.py                   ← Expose via API
```

---

## 🚀 Running the Service

### Prerequisites

- Python 3.12+
- Virtual environment with dependencies installed
- `.env` file with `DATABASE_URL` configured

### Start the Server

```bash
cd ~/projects/Recommender

# Activate virtualenv
source venv/bin/activate       # bash/zsh
source venv/bin/activate.fish  # fish shell

# Start server
uvicorn app.main:app --reload --port 8001
```

### First-Time Setup

```bash
# 1. Build indexes (run once, or use /reindex API)
python -m app.services.jury_matching.scripts.build_jury_index
python -m app.services.jury_matching.scripts.build_project_index

# 2. Test batch match
python -m app.services.jury_matching.scripts.test_batch
```

### Quick API Test

```bash
# Health check
curl http://localhost:8001/health

# Re-index (rebuilds both jury + project indexes)
curl -X POST http://localhost:8001/api/v1/jury/reindex

# Batch match (get jury recommendations for ALL projects)
curl -X POST http://localhost:8001/api/v1/jury/batch
```

---

## 🔧 Troubleshooting

### Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `Address already in use` | Port 8001 is occupied | `fuser -k 8001/tcp` then restart |
| `TimeoutError` (asyncpg) | Supabase DB is paused / cold start | Increase `command_timeout` in `db.py` to 60s. Wait 30s and retry. |
| `ModuleNotFoundError: 'app'` | Running script directly | Use `python -m app.services.jury_matching.scripts.build_jury_index` |
| `FAISS index not found` | Never ran `/reindex` | Call `POST /api/v1/jury/reindex` first |
| `All scores are low (<20)` | No domain/industry overlap | This is expected for edge cases. Flag for manual review. |
| `Same jury for every project` | Small jury pool / dominant domains | Expected when few supervisors share popular domains |

---

## ❓ FAQ

### Q: Does the AI "assign" jury members?
**No.** The AI provides a **ranked list of recommendations** per project. Your backend decides who gets assigned (handling conflicts, load balancing, etc.).

### Q: What if a jury member is recommended for 50 projects?
Your backend should implement a `MAX_ASSIGNMENTS_PER_JURY` limit. Pick the top recommendation, and if that person is full, move to the next candidate.

### Q: How often should I re-index?
- **On data change:** Supabase webhooks handle this automatically.
- **Before batch match:** If you're unsure, call `/reindex` → wait 20s → call `/batch`.

### Q: Can I change the scoring weights?
Yes. Edit `app/services/jury_matching/service.py`, look for:
```python
final_raw = ((semantic_score / 100.0) * 0.60) + (domain_score * 0.30) + (industry_score * 0.10)
```

### Q: What AI model is used?
`all-mpnet-base-v2` from Sentence Transformers (768-dimensional vectors). It runs locally on CPU — no external API calls needed.

---

## 📝 Integration Checklist

Before going live:

- [ ] AI Service running on Droplet (port 8001)
- [ ] `POST /api/v1/jury/reindex` returns `200 OK`
- [ ] `POST /api/v1/jury/batch` returns project matches
- [ ] Backend client service created (see Integration Guide above)
- [ ] Supabase webhooks configured for `projects` and `project_domains`
- [ ] Admin "Assign Jury" button wired to backend → AI service
- [ ] Load balancing logic implemented (MAX_ASSIGNMENTS_PER_JURY)
- [ ] Edge cases handled (low-score matches flagged for manual review)

---

**Created:** February 2026  
**Service:** FYPilot Jury Matching AI  
**Version:** 1.0.0  
**Port:** 8001  
**Endpoints:** `/api/v1/jury/batch`, `/api/v1/jury/reindex`
