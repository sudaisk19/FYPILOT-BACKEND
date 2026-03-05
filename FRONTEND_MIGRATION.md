# Frontend Migration Guide: `supervisor` → `faculty`

> **Source of truth:** [`implementation_plan.md.resolved`](implementation_plan.md.resolved)  
> **Backend status:** Migration complete — database, models, auth, and all API endpoints updated.  
> **Date:** 2026-03-05

This document lists every breaking change the frontend must update. Changes are grouped by impact level.

---

## 1. User Role String

The `role` field returned in auth tokens and user objects has changed.

| Old value | New value |
|-----------|-----------|
| `"supervisor"` | `"faculty"` |

**Affects:**
- Role-based conditional rendering (e.g. showing faculty nav vs student nav)
- Any `if (user.role === "supervisor")` guards → change to `"faculty"`
- Local storage / cached user objects — clear on login or handle both values during transition

---

## 2. Admin — Faculty Management Routes

All `/admin/supervisors/...` routes are now `/admin/faculty/...`.

| Old URL | New URL | Method |
|---------|---------|--------|
| `GET /api/admin/supervisors/dropdown` | `GET /api/admin/faculty/dropdown` | Get faculty dropdown list |
| `GET /api/admin/supervisors` | `GET /api/admin/faculty` | Paginated faculty list |
| `GET /api/admin/supervisors/{supervisor_id}` | `GET /api/admin/faculty/{faculty_id}` | Individual faculty profile |
| `PATCH /api/admin/supervisors/{supervisor_id}/capacity` | `PATCH /api/admin/faculty/{faculty_id}/capacity` | Update capacity |

### ⚠️ Breaking: JSON response key rename in paginated list

`GET /api/admin/faculty` response body:

```json
// BEFORE
{
  "supervisors": [...],
  "total": 10,
  "page": 1,
  ...
}

// AFTER
{
  "faculty": [...],
  "total": 10,
  "page": 1,
  ...
}
```

**Action:** Update any code reading `response.supervisors` → `response.faculty`.

### ⚠️ Breaking: Path parameter rename

| Old param | New param |
|-----------|-----------|
| `supervisor_id` (in URL) | `faculty_id` (in URL) |

**Action:** Update any URL builder that interpolates `supervisor_id` into the path.

---

## 3. Faculty Milestones Routes

The milestone routes for faculty-side have moved from `/supervisors/` prefix to `/faculty/`.

| Old URL | New URL | Method |
|---------|---------|--------|
| `GET /api/supervisors/milestones` | `GET /api/faculty/milestones` | List milestones |
| `GET /api/supervisors/milestones/{milestone_id}` | `GET /api/faculty/milestones/{milestone_id}` | Milestone detail |
| `GET /api/supervisors/milestones/{milestone_id}/evaluations` | `GET /api/faculty/milestones/{milestone_id}/evaluations` | Evaluations list |
| `POST /api/supervisors/milestones/{milestone_id}/groups/{group_id}/evaluation` | `POST /api/faculty/milestones/{milestone_id}/groups/{group_id}/evaluation` | Submit evaluation |
| `GET /api/supervisors/milestones/{milestone_id}/groups/{group_id}/evaluation` | `GET /api/faculty/milestones/{milestone_id}/groups/{group_id}/evaluation` | Get evaluation |
| `PATCH /api/supervisors/milestones/{milestone_id}/groups/{group_id}/evaluation` | `PATCH /api/faculty/milestones/{milestone_id}/groups/{group_id}/evaluation` | Update evaluation |

---

## 4. Faculty Profile Routes

Already updated in a prior sprint. Documented here for completeness.

| Old URL | New URL |
|---------|---------|
| `GET /api/supervisors/profile` | `GET /api/faculty/profile` |
| `POST /api/supervisors/wizard-profile` | `POST /api/faculty/wizard-profile` |
| `PATCH /api/supervisors/profile` | `PATCH /api/faculty/profile` |

---

## 5. Invite / Request Routes (Faculty-side)

Faculty accept/reject/view invite routes now enforce `role == "faculty"` with `is_supervisor == true`. The URL paths did **not** change — these are the same paths as before:

| URL | Notes |
|-----|-------|
| `GET /api/invites/supervisor/pending/requests` | Faculty must have `is_supervisor=true` |
| `POST /api/invites/supervisor/{request_id}/accept` | Faculty must have `is_supervisor=true` |
| `POST /api/invites/supervisor/{request_id}/reject` | Faculty must have `is_supervisor=true` |
| `GET /api/invites/supervisor/{request_id}/details` | Faculty must have `is_supervisor=true` |

**Action:** No URL change. If a faculty user gets `403` on these routes, it means their `is_supervisor` flag is `false`. Admin must set it.

---

## 6. Explore Route — Faculty Filter

`GET /api/explore/supervisors` now only returns faculty where `is_supervisor = true`. Faculty who are jury-only will not appear in student explore.

No URL change — same endpoint, stricter server-side filter.

### ⚠️ Breaking: JSON response key rename

`GET /api/explore/supervisors` response body:

```json
// BEFORE
{
  "supervisors": [...],
  "total": 10,
  "page": 1,
  ...
}

// AFTER
{
  "faculty": [...],
  "total": 10,
  "page": 1,
  ...
}
```

**Action:** Update any code reading `response.supervisors` → `response.faculty`.

---

## 7. OpenAPI / Swagger Tag Changes

Swagger UI groupings have changed. Update any generated client SDKs if tags are used as discriminators.

| Old Tag | New Tag |
|---------|---------|
| `admin-supervisors` | `admin-faculty` |
| `supervisor-milestones` | `faculty-milestones` |

---

## 8. Error Message Changes

Some error message strings in API responses have changed. If the frontend displays these to users, update accordingly.

| Old message | New message | Endpoint |
|-------------|-------------|----------|
| `"Supervisor not found"` | `"Faculty not found"` | `GET /api/admin/faculty/{faculty_id}` |
| `"Supervisor already has N assigned groups."` | `"Faculty member already has N assigned groups."` | `PATCH /api/admin/faculty/{faculty_id}/capacity` |
| `"Only supervisors can view invites"` | `"Only faculty with supervisor privileges can view invites"` | Invite endpoints |
| `"Only supervisors can accept invites"` | `"Only faculty with supervisor privileges can accept invites"` | Accept endpoint |
| `"Only supervisors can reject invites"` | `"Only faculty with supervisor privileges can reject invites"` | Reject endpoint |
| `"Only supervisors can view request details"` | `"Only faculty with supervisor privileges can view request details"` | Details endpoint |

---

## 9. Other Faculty Routes (No URL change)

The following routes still use `/supervisors/` paths but this is intentional. These are for faculty who act in a supervision capacity and the URLs remain unchanged:

| Route Category | URLs | Notes |
|----------------|------|-------|
| **Faculty Groups** | `/api/supervisors/my-groups`, `/api/supervisors/my-groups/{group_id}`, `/api/supervisors/my-groups/dropdown` | Faculty viewing groups they supervise |
| **Faculty Announcements** | `/api/supervisors/announcements`, `/api/supervisors/announcements/{id}` | Faculty creating/managing announcements |
| **Faculty Submissions** | `/api/supervisors/submissions/...` | Faculty reviewing student submissions |

**Action:** No frontend changes needed for these routes.

---

## 10. No-Change Reference (Group-Role Labels)

`GET /api/shortlist/supervisors` response body:

```json
// BEFORE
{
  "group_id": "...",
  "supervisors": [...]
}

// AFTER
{
  "group_id": "...",
  "faculty": [...]
}
```

**Action:** Update any code reading `response.supervisors` → `response.faculty`.

---

## 12. Request Body / DB Column Renames (Alembic Migration `a2b3c4d5e6f7`)

The following DB columns were renamed. Backend schemas already reflect these changes. Only matters if the frontend was sending these as raw field names in request bodies.

| Table | Old column | New column |
|-------|-----------|------------|
| `requests` | `supervisor_id` | `faculty_id` |
| `shortlisted_supervisors` | `supervisor_id` | `faculty_id` |
| `faculty_domains` | `supervisor_id` | `faculty_id` |
| `faculty_industries` | `supervisor_id` | `faculty_id` |

**Invite/request body** — the faculty invite schema already sends `faculty_id`. If any frontend call was previously passing `supervisor_id` as a request body field to invite endpoints, update it to `faculty_id`.

---

## 13. No-Change Reference (Group-Role Labels)The following strings remain **unchanged** throughout the system — they describe a *role within a group*, not the user's account role:

- `"supervisor"` and `"cosupervisor"` in group/request assignment contexts
- `body.role == "supervisor"` in invite send requests
- `TargetRoleEnum.all_supervisors` (kept alongside new `all_faculty`)

**Do not change these on the frontend.**

---

## Summary Checklist

- [ ] Replace all `user.role === "supervisor"` checks with `"faculty"`
- [ ] Update admin faculty list URL: `/admin/supervisors` → `/admin/faculty`
- [ ] Update admin faculty detail URL: `/admin/supervisors/{id}` → `/admin/faculty/{id}`
- [ ] Update admin capacity URL: `/admin/supervisors/{id}/capacity` → `/admin/faculty/{id}/capacity`
- [ ] Update admin dropdown URL: `/admin/supervisors/dropdown` → `/admin/faculty/dropdown`
- [ ] Read `response.faculty` instead of `response.supervisors` in the admin paginated list response
- [ ] Update faculty milestone URLs: `/supervisors/milestones/...` → `/faculty/milestones/...`
- [ ] **Explore page**: read `response.faculty` instead of `response.supervisors` (`GET /api/explore/supervisors`)
- [ ] **Shortlist**: read `response.faculty` instead of `response.supervisors` (`GET /api/shortlist/supervisors`)
- [ ] **Invite send**: confirm request body uses `faculty_id` (not `supervisor_id`)
- [ ] Clear cached user role values on next login
- [ ] Update any generated API client (OpenAPI SDK) if used
