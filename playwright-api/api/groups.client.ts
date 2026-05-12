import type { APIRequestContext } from "@playwright/test";

import { BaseClient } from "./base.client";

/** Group routes: router prefix `/api/groups` (app/api/http/group.py). */
export class GroupsClient extends BaseClient {
  constructor(request: APIRequestContext, token?: string) {
    super(request, token);
  }
}
