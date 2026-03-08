# 🎓 Jury Matching — Frontend Integration Guide

> Complete guide for integrating the jury assignment system into the admin panel.

**Base URL:** `/api/jury-matching`  
**Auth:** All endpoints require admin role (Bearer token)

---

## 📑 Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Full Workflow](#full-workflow)
3. [API Reference](#api-reference)
4. [Frontend Implementation Guide](#frontend-implementation-guide)
5. [Error Handling](#error-handling)

---

## 🏗️ Architecture Overview

```
┌─────────────────────┐
│   Admin Dashboard    │
│   (React Frontend)   │
└─────┬───────────────┘
      │  HTTP
      ▼
┌─────────────────────┐
│   FastAPI Backend    │  ← Wrapper + DB persistence
│   /api/jury-matching │
└─────┬───────────────┘
      │  HTTP
      ▼
┌─────────────────────┐
│   AI Microservice    │  ← All matching logic
│   (Port 8001)        │
└─────────────────────┘
```

**What the backend does:**
- Passes requests to the AI service (no processing)
- Saves AI results (pairs + assignments) to the database
- Auto-deletes all previous data when a new job starts
- Provides DELETE, PATCH, and dropdown endpoints for admin

**What the AI service does:**
- Generates jury pairs from `is_jury=true` faculty
- Assigns projects to pairs using FAISS semantic matching
- Returns pairs + assignments in one response

---

## 🔄 Full Workflow

### Happy Path (Admin assigns juries)

```
Step 1: Admin clicks "Assign Juries"
   ↓
Step 2: POST /assign  →  get back batch_id  (HTTP 202)
   ↓  ⚠️ All previous jury data is auto-deleted
Step 3: Poll GET /assign/{batch_id}/status every 2-3 seconds
   ↓
Step 4: status === "completed"  →  render assignments table
   ↓
Step 5: Admin reviews. Wants to swap a jury?
   ↓
Step 6: GET /jury-pairs  →  populate dropdown
   ↓
Step 7: PATCH /assignments/{id}/jury  →  swap the pair
```

### Manual Reset (Admin wants to clear everything)

```
DELETE /assignments  →  wipes all assignments, pairs, and batches
```

---

## 📡 API Reference

### 1. `GET /health` — Check AI service status

No auth required for this one (useful for status indicators).

**Response:**
```json
{
  "status": "healthy",
  "ai_service": "connected",
  "circuit_breaker": "closed",
  "message": "Jury Matching AI service is available"
}
```

Use `status` to show a green/red indicator on the jury page.

---

### 2. `POST /batch` — Preview AI recommendations (optional)

Get raw AI recommendations without saving anything to the database.

**Response:** Raw AI service response (schema varies — render as-is or skip this endpoint).

---

### 3. `POST /reindex` — Rebuild AI indexes

Call this if faculty or projects have changed and the AI needs to re-learn.

**Response:**
```json
{
  "status": "ok",
  "message": "Re-indexing started."
}
```

---

### 4. `POST /assign` — ⭐ Start jury assignment (main action)

**This is the primary endpoint.** Triggers the full AI matching flow.

> ⚠️ **This auto-deletes ALL existing jury data** (pairs, assignments, batches) before starting.

**Request:**
```json
{
  "max_groups_per_pair": 5,
  "min_jury_per_project": 1,
  "fyp_cycle": "fyp2"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `max_groups_per_pair` | int (1-20) | ✅ | Max projects one jury pair evaluates |
| `min_jury_per_project` | int (1-5) | No (default: 1) | Min jury pairs per project |
| `fyp_cycle` | string | ✅ | `"fyp1"` or `"fyp2"` |

**Response (HTTP 202):**
```json
{
  "batch_id": "a1b2c3d4-e5f6-...",
  "status": "processing",
  "message": "Jury assignment started (all previous data cleared). Poll GET /api/jury-matching/assign/a1b2c3d4-e5f6-.../status"
}
```

**Frontend action:** Save `batch_id`, start polling.

---

### 5. `GET /assign/{batch_id}/status` — ⭐ Poll for results

Poll this every **2-3 seconds** until `status` is `"completed"` or `"failed"`.

**Response (processing):**
```json
{
  "batch_id": "a1b2c3d4-...",
  "status": "processing",
  "fyp_cycle": "fyp2",
  "error_log": null,
  "created_at": "2026-03-09T14:30:00Z",
  "total_assigned": 0,
  "assignments": []
}
```

**Response (completed):**
```json
{
  "batch_id": "a1b2c3d4-...",
  "status": "completed",
  "fyp_cycle": "fyp2",
  "error_log": null,
  "created_at": "2026-03-09T14:30:00Z",
  "total_assigned": 15,
  "assignments": [
    {
      "id": "assignment-uuid-1",
      "project_id": "project-uuid-1",
      "project_name": "AI Disease Prediction",
      "pair_id": "pair-uuid-1",
      "jury_number": 1,
      "faculty_1_name": "Dr. Ali Khan",
      "faculty_2_name": "Dr. Sara Ahmed",
      "score": 87.5,
      "reason": "Strong domain overlap in AI and healthcare"
    },
    {
      "id": "assignment-uuid-2",
      "project_id": "project-uuid-2",
      "project_name": "Smart Traffic System",
      "pair_id": "pair-uuid-2",
      "jury_number": 2,
      "faculty_1_name": "Dr. Usman Tariq",
      "faculty_2_name": "Dr. Hina Bashir",
      "score": 72.3,
      "reason": "IoT and embedded systems expertise"
    }
  ]
}
```

**Response (failed):**
```json
{
  "batch_id": "a1b2c3d4-...",
  "status": "failed",
  "fyp_cycle": "fyp2",
  "error_log": "AI service returned no results",
  "created_at": "2026-03-09T14:30:00Z",
  "total_assigned": 0,
  "assignments": []
}
```

**Frontend action:**
- `"processing"` → show spinner, keep polling
- `"completed"` → stop polling, render table from `assignments`
- `"failed"` → stop polling, show `error_log` in a toast/alert

---

### 6. `GET /jury-pairs` — Jury pair dropdown

Returns all jury pairs for a `<Select>` dropdown when admin wants to manually change a project's jury.

**Response:**
```json
[
  {
    "jury_id": "pair-uuid-1",
    "label": "Jury 1 — Dr. Ali Khan & Dr. Sara Ahmed",
    "faculty_1_name": "Dr. Ali Khan",
    "faculty_2_name": "Dr. Sara Ahmed"
  },
  {
    "jury_id": "pair-uuid-2",
    "label": "Jury 2 — Dr. Usman Tariq & Dr. Hina Bashir",
    "faculty_1_name": "Dr. Usman Tariq",
    "faculty_2_name": "Dr. Hina Bashir"
  }
]
```

**Frontend:** Map directly to dropdown options → `value = jury_id`, `label = label`.

---

### 7. `PATCH /assignments/{assignment_id}/jury` — ⭐ Swap jury pair

Change the jury pair for a specific project assignment.

**Request:**
```json
{
  "pair_id": "pair-uuid-2"
}
```

**Response:**
```json
{
  "id": "assignment-uuid-1",
  "project_id": "project-uuid-1",
  "old_pair_id": "pair-uuid-1",
  "new_pair_id": "pair-uuid-2",
  "message": "Jury assignment updated successfully"
}
```

---

### 8. `DELETE /assignments` — Clear all jury data

Completely wipes assignments, pairs, and batches.

**Response:**
```json
{
  "message": "All jury data cleared successfully",
  "deleted_assignments": 15,
  "deleted_pairs": 5,
  "deleted_batches": 1
}
```

---

### 9. `GET /assignments` — List all batches

Returns all batches (most recent first). Useful for history.

**Response:**
```json
[
  {
    "batch_id": "a1b2c3d4-...",
    "status": "completed",
    "fyp_cycle": "fyp2",
    "error_log": null,
    "created_at": "2026-03-09T14:30:00Z",
    "total_assigned": 0,
    "assignments": []
  }
]
```

> Note: `assignments` array is empty in the list view. Use `GET /assign/{batch_id}/status` to get full assignment details.

---

## 🖥️ Frontend Implementation Guide

### Page Layout Suggestion

```
┌─────────────────────────────────────────────────────────┐
│  Jury Assignment                          [AI: 🟢 Healthy] │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  FYP Cycle: [FYP1 ▾]   Max Groups/Pair: [5]            │
│                                                         │
│  [🚀 Assign Juries]              [🗑️ Clear All]         │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────┬──────────────────┬──────────────┬────────┐ │
│  │ Project │ Jury Pair        │ Score        │ Action │ │
│  ├─────────┼──────────────────┼──────────────┼────────┤ │
│  │ AI Pred │ Jury 1 — Dr. A   │ 87.5         │ [Edit] │ │
│  │         │ & Dr. B          │              │        │ │
│  ├─────────┼──────────────────┼──────────────┼────────┤ │
│  │ Traffic │ Jury 2 — Dr. C   │ 72.3         │ [Edit] │ │
│  │ System  │ & Dr. D          │              │        │ │
│  └─────────┴──────────────────┴──────────────┴────────┘ │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### React Pseudocode — Assign + Poll

```tsx
const handleAssign = async () => {
  setLoading(true);

  // Step 1: Trigger assignment
  const { batch_id } = await api.post("/jury-matching/assign", {
    max_groups_per_pair: maxGroups,
    min_jury_per_project: minJury,
    fyp_cycle: selectedCycle,
  });

  // Step 2: Poll for status
  const poll = setInterval(async () => {
    const result = await api.get(`/jury-matching/assign/${batch_id}/status`);

    if (result.status === "completed") {
      clearInterval(poll);
      setAssignments(result.assignments);
      setLoading(false);
      toast.success(`${result.total_assigned} assignments created`);
    }

    if (result.status === "failed") {
      clearInterval(poll);
      setLoading(false);
      toast.error(result.error_log || "Assignment failed");
    }
  }, 3000); // Poll every 3 seconds
};
```

### React Pseudocode — Edit Jury (Dropdown + Patch)

```tsx
const handleEditJury = async (assignmentId: string) => {
  // Step 1: Fetch dropdown options
  const pairs = await api.get("/jury-matching/jury-pairs");
  setDropdownOptions(pairs); // [{ jury_id, label, ... }]
  setEditingId(assignmentId);
  setModalOpen(true);
};

const handleSaveJury = async (assignmentId: string, newPairId: string) => {
  const result = await api.patch(
    `/jury-matching/assignments/${assignmentId}/jury`,
    { pair_id: newPairId }
  );
  toast.success(result.message);
  // Refresh the assignments table
};
```

---

## ⚠️ Error Handling

| HTTP Code | Meaning | Frontend Action |
|-----------|---------|-----------------|
| `202` | Job started (polling required) | Start polling with `batch_id` |
| `400` | Bad input (invalid `fyp_cycle`, bad UUID) | Show validation error |
| `403` | Not an admin | Redirect to unauthorized page |
| `404` | Batch or assignment not found | Show "not found" message |
| `502` | AI service returned an error | Show "AI service error" toast |
| `503` | AI service is down | Show "AI service unavailable" banner |
| `504` | AI service timed out | Show "Request timed out, try again" |
| `500` | Unexpected server error | Show generic error toast |

### Confirm Before Destructive Actions

Always show a confirmation dialog before:
- **`POST /assign`** — "This will delete all existing jury assignments. Continue?"
- **`DELETE /assignments`** — "This will permanently clear all jury data. Are you sure?"

---

*Generated for FYPilot Frontend Team — March 2026*
