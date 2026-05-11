import type { APIRequestContext } from "@playwright/test";

import { BaseClient, type CachedApiResponse } from "./base.client";

/** Admin routes: `admin_dashboard.py`, `admin_students.py`, etc. */
export class AdminClient extends BaseClient {
  constructor(request: APIRequestContext, token?: string) {
    super(request, token);
  }

  getDashboardInsights(): Promise<CachedApiResponse> {
    return this.get("/api/admin/dashboard/insights");
  }

  listStudents(page = 1, perPage = 10): Promise<CachedApiResponse> {
    return this.get(
      `/api/admin/students?page=${page}&per_page=${perPage}&group=all`,
    );
  }

  listStudentsInvalidPage(): Promise<CachedApiResponse> {
    return this.get("/api/admin/students?page=0&per_page=10&group=all");
  }

  toggleStudentActive(
    userId: string,
    body: Record<string, unknown>,
  ): Promise<CachedApiResponse> {
    return this.patch(`/api/admin/students/${userId}/toggle-active`, {
      data: body,
    });
  }
}
