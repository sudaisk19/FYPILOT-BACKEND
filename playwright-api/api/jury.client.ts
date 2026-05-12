import type { APIRequestContext } from "@playwright/test";

import { BaseClient, type CachedApiResponse } from "./base.client";

/**
 * Admin jury orchestration (`jury_matching.py`).
 * Skipped in tests: AI/LLM batch, reindex, assign POST, health ping, destructive DELETE.
 */
export class JuryClient extends BaseClient {
  constructor(request: APIRequestContext, token?: string) {
    super(request, token);
  }

  listJuryPairs(): Promise<CachedApiResponse> {
    return this.get("/api/jury-matching/jury-pairs");
  }

  getAssignmentBatchStatus(batchId: string): Promise<CachedApiResponse> {
    return this.get(`/api/jury-matching/assign/${batchId}/status`);
  }

  listAssignments(): Promise<CachedApiResponse> {
    return this.get("/api/jury-matching/assignments");
  }
}
