import type { APIRequestContext, APIResponse } from "@playwright/test";
import * as allure from "allure-js-commons";

import {
  attachRequest,
  attachResponse,
  attachToken,
} from "../utils/allure.helper";

export type JsonRecord = Record<string, unknown>;

/**
 * Playwright allows only one read of the response body; we cache text so callers
 * can call `.json()` / `.text()` without breaking attachments.
 */
export class CachedApiResponse {
  constructor(
    private readonly inner: APIResponse,
    private readonly bodyText: string,
  ) {}

  status(): number {
    return this.inner.status();
  }

  ok(): boolean {
    return this.inner.ok();
  }

  headers(): { [key: string]: string } {
    return this.inner.headers();
  }

  url(): string {
    return this.inner.url();
  }

  async text(): Promise<string> {
    return this.bodyText;
  }

  async json(): Promise<unknown> {
    const t = this.bodyText.trim();
    if (!t) {
      return null;
    }
    return JSON.parse(t) as unknown;
  }

  /** Cached response body (single read). */
  getBodyText(): string {
    return this.bodyText;
  }
}

export class BaseClient {
  protected bearerToken: string | undefined;

  constructor(
    protected readonly request: APIRequestContext,
    token?: string,
  ) {
    this.bearerToken = token;
  }

  setBearerToken(token: string | undefined): void {
    this.bearerToken = token;
  }

  protected authHeaders(
    extra?: Record<string, string>,
  ): Record<string, string> {
    const h: Record<string, string> = {
      Accept: "application/json",
      ...extra,
    };
    if (this.bearerToken) {
      h.Authorization = `Bearer ${this.bearerToken}`;
    }
    return h;
  }

  private logLine(method: string, url: string, status: number): void {
    console.log(`[API] ${method} ${url} -> ${status}`);
  }

  private async attachAllureExchange(
    method: string,
    requestUrl: string,
    requestBody: unknown,
    responseStatus: number,
    responseBodyText: string,
  ): Promise<void> {
    const requestBodyValue =
      requestBody === undefined
        ? "null"
        : JSON.stringify(requestBody, null, 2);
    await allure.attachment(
      "Request Body",
      requestBodyValue,
      "application/json",
    );

    let responseBodyValue = responseBodyText;
    try {
      const parsed = JSON.parse(responseBodyText);
      responseBodyValue = JSON.stringify(parsed, null, 2);
    } catch {
      // Keep raw text body for non-JSON responses.
    }
    await allure.attachment("Response Body", responseBodyValue, "application/json");
    await allure.parameter("Status Code", String(responseStatus));
    await allure.parameter("Endpoint", requestUrl);
    await allure.parameter("Method", method);
  }

  private async finalizeResponse(
    method: string,
    requestUrl: string,
    requestBody: unknown,
    response: APIResponse,
  ): Promise<CachedApiResponse> {
    const bodyText = await response.text();
    await attachResponse(response.status(), bodyText);
    await this.attachAllureExchange(
      method,
      requestUrl,
      requestBody,
      response.status(),
      bodyText,
    );
    this.logLine(method, requestUrl, response.status());
    return new CachedApiResponse(response, bodyText);
  }

  async get(
    url: string,
    options?: { headers?: Record<string, string> },
  ): Promise<CachedApiResponse> {
    return allure.step(`GET ${url}`, async () => {
      const headers = this.authHeaders(options?.headers);
      if (this.bearerToken) {
        await attachToken(this.bearerToken);
      }
      await attachRequest("GET", url, undefined);
      const response = await this.request.get(url, { headers });
      return this.finalizeResponse("GET", url, undefined, response);
    });
  }

  async post(
    url: string,
    options?: { data?: unknown; headers?: Record<string, string> },
  ): Promise<CachedApiResponse> {
    return allure.step(`POST ${url}`, async () => {
      const headers = this.authHeaders(options?.headers);
      if (this.bearerToken) {
        await attachToken(this.bearerToken);
      }
      await attachRequest("POST", url, options?.data);
      const postOpts: Parameters<APIRequestContext["post"]>[1] = { headers };
      if (options?.data !== undefined) {
        postOpts.data = options.data as object | string;
      }
      const response = await this.request.post(url, postOpts);
      return this.finalizeResponse("POST", url, options?.data, response);
    });
  }

  async put(
    url: string,
    options?: { data?: unknown; headers?: Record<string, string> },
  ): Promise<CachedApiResponse> {
    return allure.step(`PUT ${url}`, async () => {
      const headers = this.authHeaders(options?.headers);
      if (this.bearerToken) {
        await attachToken(this.bearerToken);
      }
      await attachRequest("PUT", url, options?.data);
      const putOpts: Parameters<APIRequestContext["put"]>[1] = { headers };
      if (options?.data !== undefined) {
        putOpts.data = options.data as object | string;
      }
      const response = await this.request.put(url, putOpts);
      return this.finalizeResponse("PUT", url, options?.data, response);
    });
  }

  async patch(
    url: string,
    options?: { data?: unknown; headers?: Record<string, string> },
  ): Promise<CachedApiResponse> {
    return allure.step(`PATCH ${url}`, async () => {
      const headers = this.authHeaders(options?.headers);
      if (this.bearerToken) {
        await attachToken(this.bearerToken);
      }
      await attachRequest("PATCH", url, options?.data);
      const patchOpts: Parameters<APIRequestContext["patch"]>[1] = { headers };
      if (options?.data !== undefined) {
        patchOpts.data = options.data as object | string;
      }
      const response = await this.request.patch(url, patchOpts);
      return this.finalizeResponse("PATCH", url, options?.data, response);
    });
  }

  async delete(
    url: string,
    options?: { data?: unknown; headers?: Record<string, string> },
  ): Promise<CachedApiResponse> {
    return allure.step(`DELETE ${url}`, async () => {
      const headers = this.authHeaders(options?.headers);
      if (this.bearerToken) {
        await attachToken(this.bearerToken);
      }
      await attachRequest("DELETE", url, options?.data);
      const deleteOpts: Parameters<APIRequestContext["delete"]>[1] = { headers };
      if (options?.data !== undefined) {
        deleteOpts.data = options.data as object | string;
      }
      const response = await this.request.delete(url, deleteOpts);
      return this.finalizeResponse("DELETE", url, options?.data, response);
    });
  }
}
