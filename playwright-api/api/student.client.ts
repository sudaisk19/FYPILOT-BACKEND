import type { APIRequestContext } from "@playwright/test";

import { BaseClient, type CachedApiResponse } from "./base.client";

/** Student HTTP surface: `app/api/http/student_*.py` mounted under `/api` in `router.py`. */
export class StudentClient extends BaseClient {
  constructor(request: APIRequestContext, token?: string) {
    super(request, token);
  }

  getProfile(): Promise<CachedApiResponse> {
    return this.get("/api/students/profile");
  }

  getDashboardInsights(): Promise<CachedApiResponse> {
    return this.get("/api/students/dashboard/insights");
  }

  listMilestones(): Promise<CachedApiResponse> {
    return this.get("/api/students/milestones");
  }

  getMilestone(milestoneId: string): Promise<CachedApiResponse> {
    return this.get(`/api/students/milestones/${milestoneId}`);
  }

  listSupervisorAnnouncements(
    page = 1,
    perPage = 10,
  ): Promise<CachedApiResponse> {
    return this.get(
      `/api/students/announcements/supervisor?page=${page}&per_page=${perPage}`,
    );
  }

  /** Invalid `page` for 422-style validation coverage on GET routes. */
  listSupervisorAnnouncementsInvalidPage(): Promise<CachedApiResponse> {
    return this.get("/api/students/announcements/supervisor?page=0&per_page=10");
  }

  listOfficialSubmissions(page = 1, perPage = 10): Promise<CachedApiResponse> {
    return this.get(
      `/api/students/submissions/official?page=${page}&per_page=${perPage}`,
    );
  }

  getOfficialSubmission(submissionId: string): Promise<CachedApiResponse> {
    return this.get(`/api/students/submissions/official/${submissionId}`);
  }

  listDocumentTypes(): Promise<CachedApiResponse> {
    return this.get("/api/students/document-types");
  }

  postWizardProfile(body: unknown): Promise<CachedApiResponse> {
    return this.post("/api/students/wizard-profile", { data: body });
  }
}
