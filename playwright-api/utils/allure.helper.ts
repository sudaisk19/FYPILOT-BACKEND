import {
  attachment,
  ContentType,
  parameter,
  step,
} from "allure-js-commons";

function stringifyBody(body: unknown): string {
  if (body === undefined || body === null) {
    return "";
  }
  if (typeof body === "string") {
    return body;
  }
  try {
    return JSON.stringify(body, null, 2);
  } catch {
    return String(body);
  }
}

/** Attach outgoing API request metadata (method, URL, optional body). */
export async function attachRequest(
  method: string,
  url: string,
  body: unknown,
): Promise<void> {
  const payload = {
    method,
    url,
    body: body === undefined ? null : body,
  };
  await attachment(
    `request-${method}-${safeSlug(url)}`,
    stringifyBody(payload),
    ContentType.JSON,
  );
}

/** Attach HTTP response status and body text. */
export async function attachResponse(
  status: number,
  body: string | unknown,
): Promise<void> {
  const bodyStr = typeof body === "string" ? body : stringifyBody(body);
  await attachment(
    `response-${status}`,
    JSON.stringify({ status, body: bodyStr }, null, 2),
    ContentType.JSON,
  );
  await parameter("http_status", String(status));
}

/** Attach bearer token with masking (never log full secrets). */
export async function attachToken(token: string): Promise<void> {
  const masked =
    token.length <= 12
      ? "***"
      : `${token.slice(0, 4)}…${token.slice(-4)} (len=${token.length})`;
  await attachment("authorization-bearer", masked, ContentType.TEXT);
}

/**
 * Wrap Allure `step` with the project's naming — maps directly to `step` from
 * allure-js-commons (callback receives StepContext).
 */
export async function logStep<T>(
  name: string,
  fn: () => Promise<T>,
): Promise<T> {
  return step(name, async () => fn());
}

function safeSlug(url: string): string {
  return url.replace(/[^a-zA-Z0-9]+/g, "_").slice(0, 80);
}
