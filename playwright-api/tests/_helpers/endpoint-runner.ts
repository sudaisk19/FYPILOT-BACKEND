import { expect } from "@playwright/test";
import * as allure from "allure-js-commons";

import type { BaseClient } from "../../api/base.client";
import { HTTP } from "../../constants/http.constants";
import { test } from "../../fixtures/auth.fixture";
import type { RoleTokens } from "../../fixtures/auth.fixture";
import {
  expectUnauthorizedOrForbidden,
  requestWithoutAuth,
} from "./api-scenarios";

export type RoleName = "student" | "faculty" | "admin";

export type MatrixRow = {
  name: string;
  method: "GET" | "POST" | "PATCH" | "DELETE";
  path: string;
  role: RoleName;
  wrongRole: RoleName;
  /** When true, skip wrong-role test (endpoint allows any authenticated user). */
  skipWrongRole?: boolean;
  skip?: string;
  query?: string;
  body?: unknown;
  happyStatuses: number[];
  /** When false, skip not_found test (no resource id in path). */
  supportsNotFound?: boolean;
  /** Override path for 404 probe (interpolated with ids). */
  notFoundPath?: string;
  invalidBody?: unknown;
  /** GET: append `&page=0` style fragment (include leading &) */
  invalidQueryAppend?: string;
  /** Happy path: assert these keys exist on the JSON object root. */
  expectObjectKeys?: string[];
  /** Happy path: assert body parses to a non-empty array. */
  expectJsonArray?: boolean;
};

type Ctx = { student: BaseClient; faculty: BaseClient; admin: BaseClient };

function pick(ctx: Ctx, role: RoleName): BaseClient {
  if (role === "student") {
    return ctx.student;
  }
  if (role === "faculty") {
    return ctx.faculty;
  }
  return ctx.admin;
}

function hasToken(t: RoleTokens, role: RoleName): boolean {
  if (role === "student") {
    return Boolean(t.student);
  }
  if (role === "faculty") {
    return Boolean(t.supervisor);
  }
  return Boolean(t.admin);
}

export function interpolate(
  path: string,
  ids: Record<string, string> | undefined,
): string {
  let out = path;
  if (ids) {
    for (const [k, v] of Object.entries(ids)) {
      out = out.split(`{${k}}`).join(v);
    }
  }
  return out.replace(
    /\{fake_uuid\}/g,
    ids?.fake_uuid ?? "00000000-0000-4000-8000-000000000099",
  );
}

async function call(
  client: BaseClient,
  method: MatrixRow["method"],
  url: string,
  body?: unknown,
) {
  if (method === "GET") {
    return client.get(url);
  }
  if (method === "POST") {
    return client.post(url, { data: body });
  }
  if (method === "PATCH") {
    return client.patch(url, { data: body });
  }
  return client.delete(url, body !== undefined ? { data: body } : undefined);
}

export function registerEndpointMatrix(
  suiteTitle: string,
  rows: MatrixRow[],
  ids: Record<string, string>,
): void {
  const featureName = suiteTitle.replace(/\s+HTTP API$/i, "").trim();
  const moduleTag = featureName.toLowerCase();

  async function annotate(
    scenario: string,
    row: MatrixRow,
    severity: "critical" | "normal" | "minor",
  ): Promise<void> {
    await allure.epic("FYPilot API Tests");
    await allure.feature(featureName);
    await allure.story(`${row.name} — ${scenario}`);
    await allure.tags(moduleTag, "api", "regression");
    await allure.owner("QA");
    await allure.severity(severity);
  }

  test.describe(suiteTitle, () => {
    test.beforeEach(async ({}, testInfo) => {
      await allure.step("Test started", async () => {
        await allure.parameter("Test Name", testInfo.title);
      });
    });

    test.afterEach(async ({}, testInfo) => {
      await allure.step("Test completed", async () => {
        await allure.parameter("Result", testInfo.status ?? "unknown");
      });
    });

    for (const row of rows) {
      if (row.skip) {
        test.describe.skip(`${row.method} ${row.path} — ${row.name}`, () => {
          test(row.skip!, () => {});
        });
        continue;
      }

      const pathInterpolated = interpolate(row.path, ids);
      const q = row.query ?? "";
      const fullPath = `${pathInterpolated}${q}`;

      test.describe(`${row.method} ${pathInterpolated} — ${row.name}`, () => {
        test("happy_path", async ({
          studentAPI,
          supervisorAPI,
          adminAPI,
          roleTokens,
        }) => {
          await annotate("Happy path", row, "critical");
          if (!hasToken(roleTokens, row.role)) {
            test.skip();
          }
          const ctx: Ctx = {
            student: studentAPI,
            faculty: supervisorAPI,
            admin: adminAPI,
          };
          const r = await call(pick(ctx, row.role), row.method, fullPath, row.body);
          const st = r.status();
          expect(row.happyStatuses).toContain(st);
          const okForShape = st === HTTP.OK || st === HTTP.CREATED;
          if (okForShape && row.expectObjectKeys?.length) {
            const body = (await r.json()) as Record<string, unknown>;
            for (const k of row.expectObjectKeys) {
              expect(body).toHaveProperty(k);
            }
          }
          if (okForShape && row.expectJsonArray) {
            const body = await r.json();
            expect(Array.isArray(body)).toBeTruthy();
          }
        });

        test("auth_missing", async ({ request }) => {
          await annotate("Auth missing", row, "normal");
          if (row.method === "DELETE") {
            const res = await request.delete(fullPath, {
              headers: { Accept: "application/json" },
            });
            expectUnauthorizedOrForbidden(res.status());
            return;
          }
          const lower = row.method.toLowerCase() as "get" | "post" | "patch";
          const r = await requestWithoutAuth(request, lower, fullPath, {
            data: row.body,
          });
          expectUnauthorizedOrForbidden(r.status());
        });

        test("wrong_role", async ({
          studentAPI,
          supervisorAPI,
          adminAPI,
          roleTokens,
        }) => {
          await annotate("Wrong role", row, "normal");
          if (row.skipWrongRole) {
            test.skip();
          }
          if (!hasToken(roleTokens, row.wrongRole) || row.wrongRole === row.role) {
            test.skip();
          }
          const ctx: Ctx = {
            student: studentAPI,
            faculty: supervisorAPI,
            admin: adminAPI,
          };
          const r = await call(pick(ctx, row.wrongRole), row.method, fullPath, row.body);
          expect(r.status()).toBe(HTTP.FORBIDDEN);
        });

        test("not_found_or_guard", async ({
          studentAPI,
          supervisorAPI,
          adminAPI,
          roleTokens,
        }) => {
          await annotate("Not found", row, "minor");
          const autoNf =
            row.supportsNotFound ?? /\{[a-zA-Z0-9_]+\}/.test(row.path);
          if (row.supportsNotFound === false || !autoNf) {
            test.skip();
          }
          if (
            row.method !== "GET" &&
            row.method !== "PATCH" &&
            row.method !== "DELETE"
          ) {
            test.skip();
          }
          if (!hasToken(roleTokens, row.role)) {
            test.skip();
          }
          const nf = row.notFoundPath
            ? interpolate(row.notFoundPath, ids) + (row.query ?? "")
            : interpolate(
                row.path.replace(/\{[^}]+\}/g, "{fake_uuid}"),
                ids,
              ) + (row.query ?? "");
          const ctx: Ctx = {
            student: studentAPI,
            faculty: supervisorAPI,
            admin: adminAPI,
          };
          const r = await call(
            pick(ctx, row.role),
            row.method,
            nf,
            row.method === "PATCH" ? row.body : undefined,
          );
          expect(
            [HTTP.NOT_FOUND, HTTP.FORBIDDEN, HTTP.BAD_REQUEST] as number[],
          ).toContain(r.status());
        });

        test("invalid_body_or_query", async ({
          studentAPI,
          supervisorAPI,
          adminAPI,
          roleTokens,
        }) => {
          await annotate("Invalid body or query", row, "minor");
          if (!hasToken(roleTokens, row.role)) {
            test.skip();
          }
          const ctx: Ctx = {
            student: studentAPI,
            faculty: supervisorAPI,
            admin: adminAPI,
          };
          if (row.method === "GET" && row.invalidQueryAppend) {
            const r = await pick(ctx, row.role).get(
              `${fullPath}${row.invalidQueryAppend}`,
            );
            expect(r.status()).toBe(HTTP.UNPROCESSABLE);
            return;
          }
          if (
            (row.method === "POST" || row.method === "PATCH") &&
            row.invalidBody !== undefined
          ) {
            const r = await call(
              pick(ctx, row.role),
              row.method,
              fullPath,
              row.invalidBody,
            );
            expect([HTTP.UNPROCESSABLE, HTTP.BAD_REQUEST] as number[]).toContain(
              r.status(),
            );
            return;
          }
          test.skip();
        });
      });
    }
  });
}
