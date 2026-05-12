import type { APIResponse } from "@playwright/test";

/** Read response as text once (single consume). */
export async function readResponseText(response: APIResponse): Promise<string> {
  try {
    return await response.text();
  } catch {
    return "";
  }
}

/** Parse JSON from cached response text. */
export function parseJsonFromText<T = unknown>(text: string): T {
  if (!text.trim()) {
    throw new Error("Empty response body");
  }
  return JSON.parse(text) as T;
}
