import type { APIRequestContext } from "@playwright/test";

import { BaseClient, type CachedApiResponse } from "./base.client";

/** Faculty / supervisor routes: `faculty_dashboard.py`, `supervisor_profile.py`, `supervisor_fypmilestone.py`. */
export class FacultyClient extends BaseClient {
  constructor(request: APIRequestContext, token?: string) {
    super(request, token);
  }

  getProfile(): Promise<CachedApiResponse> {
    return this.get("/api/faculty/profile");
  }

  getDashboardInsights(): Promise<CachedApiResponse> {
    return this.get("/api/faculty/dashboard/insights");
  }

  listMilestones(fypCycle?: string): Promise<CachedApiResponse> {
    const q = fypCycle ? `?fyp_cycle=${encodeURIComponent(fypCycle)}` : "";
    return this.get(`/api/faculty/milestones${q}`);
  }

  listMilestonesInvalidQuery(): Promise<CachedApiResponse> {
    return this.get("/api/faculty/milestones?fyp_cycle=not_a_cycle");
  }

  getMilestone(milestoneId: string): Promise<CachedApiResponse> {
    return this.get(`/api/faculty/milestones/${milestoneId}`);
  }

  postWizardProfile(body: unknown): Promise<CachedApiResponse> {
    return this.post("/api/faculty/wizard-profile", { data: body });
  }
}
