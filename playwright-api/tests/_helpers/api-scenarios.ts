import { expect, type APIRequestContext, type APIResponse } from "@playwright/test";

import { CachedApiResponse } from "../../api/base.client";
import { HTTP } from "../../constants/http.constants";

/** Random UUID v4-shaped string for 404 probes. */
export const FAKE_UUID = "00000000-0000-4000-8000-000000000099";

export async function requestWithoutAuth(
  request: APIRequestContext,
  method: "get" | "post" | "patch",
  path: string,
  options?: { data?: unknown },
): Promise<CachedApiResponse> {
  const headers = { Accept: "application/json" };
  let response;
  if (method === "get") {
    response = await request.get(path, { headers });
  } else if (method === "post") {
    response = await request.post(path, {
      headers: { ...headers, "Content-Type": "application/json" },
      data: options?.data as object,
    });
  } else {
    response = await request.patch(path, {
      headers: { ...headers, "Content-Type": "application/json" },
      data: options?.data as object,
    });
  }
  const text = await response.text();
  return new CachedApiResponse(response as APIResponse, text);
}

export function expectUnauthorizedOrForbidden(status: number): void {
  expect([HTTP.UNAUTHORIZED, HTTP.FORBIDDEN] as number[]).toContain(status);
}
