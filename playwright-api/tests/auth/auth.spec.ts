/**
 * @module Auth
 * @description Tests for authentication endpoints:
 * signup, login, /me, forgot-password
 * Paths and envelopes align with app/auth/routes.py and app/core/exceptions (JSON error wrapper).
 */

import { expect, test } from "@playwright/test";
import type { APIRequestContext } from "@playwright/test";
import * as allure from "allure-js-commons";
import { ContentType } from "allure-js-commons";

import {
  AuthClient,
  type LoginPayload,
  type SignupPayload,
} from "../../api/auth.client";
import type { CachedApiResponse } from "../../api/base.client";
import { HTTP } from "../../constants/http.constants";
import { attachRequest, attachResponse } from "../../utils/allure.helper";
import authData from "../../test-data/auth.data.json";

const SEED_PASSWORD = authData.valid.signup.password;

type InvalidRow = {
  case: string;
  data: unknown;
  expected_status?: number;
  note?: string;
};

async function readEnvelope(response: CachedApiResponse): Promise<
  Record<string, unknown>
> {
  const j = await response.json();
  return j && typeof j === "object"
    ? (j as Record<string, unknown>)
    : {};
}

/** Single Allure attachment with full request + response (BaseClient also attaches per hop). */
async function attachExchange(
  method: string,
  path: string,
  requestBody: unknown,
  response: CachedApiResponse,
): Promise<void> {
  await allure.attachment(
    `exchange-${method}-${path.replace(/[^\w]+/g, "_")}`,
    JSON.stringify(
      {
        method,
        path,
        request: requestBody ?? null,
        status: response.status(),
        responseBody: response.getBodyText(),
      },
      null,
      2,
    ),
    ContentType.JSON,
  );
}

test.describe("Auth Module", () => {
  const createdUserIds: string[] = [];
  /** Guaranteed-existing account for login / forgot-password (seeded in beforeAll). */
  let seedEmail = "";
  /** Dedicated API context for seeding — Playwright forbids reusing test `request` from beforeAll inside tests. */
  let seedContext: APIRequestContext | undefined;

  test.beforeAll(async ({ playwright }) => {
    await allure.step("Open APIRequestContext for seed user", async () => {
      seedContext = await playwright.request.newContext({
        baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8000",
        extraHTTPHeaders: { Accept: "application/json" },
      });
    });

    await allure.step("Seed user for login / forgot-password tests", async () => {
      const client = new AuthClient(seedContext!);
      seedEmail = `playwright.seed.${Date.now()}@example.com`;
      const signupPayload: SignupPayload = {
        full_name: authData.valid.signup.full_name,
        email: seedEmail,
        password: SEED_PASSWORD,
        role: authData.valid.signup.role as SignupPayload["role"],
      };
      const res = await client.signup(signupPayload);
      if (res.status() !== HTTP.CREATED) {
        throw new Error(
          `Seed signup failed: ${res.status()} — ${res.getBodyText()}`,
        );
      }
      const body = await readEnvelope(res);
      const uid = body.user as Record<string, unknown> | undefined;
      if (uid?.user_id) {
        createdUserIds.push(String(uid.user_id));
      }
    });
  });

  test.afterAll(async () => {
    await allure.step("Cleanup (best-effort) and dispose seed context", async () => {
      if (seedContext) {
        const c = new AuthClient(seedContext);
        for (const id of createdUserIds) {
          await c.deleteTestUser(id);
        }
        await seedContext.dispose();
        seedContext = undefined;
      }
    });
  });

  test.beforeEach(async ({}, testInfo) => {
    await allure.step("Test started", async () => {
      await allure.parameter("Test Name", testInfo.title);
      await allure.tags("auth", "api", "regression");
      await allure.owner("QA");
    });
    console.log(`▶ Starting: ${testInfo.title}`);
  });

  test.afterEach(async ({}, testInfo) => {
    await allure.step("Test completed", async () => {
      await allure.parameter("Result", testInfo.status ?? "unknown");
    });
    console.log(
      `${testInfo.status === "passed" ? "✅" : "❌"} ${testInfo.title}`,
    );
  });

  test.describe("POST /auth/signup", () => {
    const feature = "Register";

    test("should_return_201_and_safe_user_payload_when_signup_valid", async ({
      request,
    }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Successful signup returns JWT and user without secrets");
      await allure.severity("critical");

      const client = new AuthClient(request);
      const payload: SignupPayload = {
        ...authData.valid.signup,
        email: `apitest.${Date.now()}@example.com`,
        role: authData.valid.signup.role as SignupPayload["role"],
      };

      await allure.step("POST /auth/signup with valid UserCreate body", async () => {
        const response = await client.signup(payload);
        await attachExchange("POST", "/auth/signup", payload, response);

        await allure.step("Expect 201 Created", async () => {
          expect(response.status()).toBe(HTTP.CREATED);
        });

        await allure.step("Expect SignupResponse shape", async () => {
          const body = await readEnvelope(response);
          expect(body.access_token).toBeTruthy();
          expect(body.token_type).toBe("bearer");
          expect(body.role).toBeTruthy();
          expect(body.user).toBeDefined();
          const u = body.user as Record<string, unknown>;
          expect(u).toHaveProperty("user_id");
          expect(u).toHaveProperty("email");
          expect(u).toHaveProperty("full_name");
          expect(u).not.toHaveProperty("password");
          expect(u).not.toHaveProperty("password_hash");
          if (u.user_id) {
            createdUserIds.push(String(u.user_id));
          }
        });
      });
    });

    test("should_return_400_when_email_already_registered", async ({
      request,
    }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Duplicate signup — 400 Email already registered");
      await allure.severity("critical");

      const client = new AuthClient(request);
      const email = `dup.${Date.now()}@example.com`;
      const payload: SignupPayload = {
        ...authData.valid.signup,
        email,
        role: authData.valid.signup.role as SignupPayload["role"],
      };

      await allure.step("First signup succeeds", async () => {
        const first = await client.signup(payload);
        await attachExchange("POST", "/auth/signup", payload, first);
        await allure.step("Expect 201", async () => {
          expect(first.status()).toBe(HTTP.CREATED);
        });
        const body = await readEnvelope(first);
        const u = body.user as Record<string, unknown> | undefined;
        if (u?.user_id) {
          createdUserIds.push(String(u.user_id));
        }
      });

      await allure.step("Second signup with same email returns 400", async () => {
        const second = await client.signup(payload);
        await attachExchange("POST", "/auth/signup", payload, second);
        await allure.step("Expect 400", async () => {
          expect(second.status()).toBe(HTTP.BAD_REQUEST);
        });
        await allure.step("Expect application error envelope", async () => {
          const err = await readEnvelope(second);
          expect(String(err.error ?? "")).toContain("Email already registered");
        });
      });
    });

    for (const row of authData.invalid.missing_fields as InvalidRow[]) {
      test(`should_return_expected_status_when_${row.case}`, async ({
        request,
      }) => {
        await allure.epic("Auth");
        await allure.feature(feature);
        await allure.story(`Validation: ${row.case}`);
        await allure.severity("normal");
        await allure.parameter("case", row.case);
        if (row.note) {
          await allure.parameter("note", row.note);
        }

        const expected =
          row.expected_status ?? HTTP.UNPROCESSABLE;
        const payload = row.data as unknown as SignupPayload;

        await allure.step("POST /auth/signup with invalid body", async () => {
          const client = new AuthClient(request);
          const response = await client.signup(payload);
          await attachExchange("POST", "/auth/signup", payload, response);
          await allure.step(`Expect ${expected}`, async () => {
            expect(response.status()).toBe(expected);
          });
        });
      });
    }

    for (const row of authData.invalid.wrong_types as InvalidRow[]) {
      test(`should_return_422_when_${row.case}`, async ({ request }) => {
        await allure.epic("Auth");
        await allure.feature(feature);
        await allure.story(`Wrong types: ${row.case}`);
        await allure.severity("normal");
        await allure.parameter("case", row.case);

        const expected = row.expected_status ?? HTTP.UNPROCESSABLE;
        const payload = row.data as unknown as SignupPayload;

        await allure.step("POST /auth/signup with wrong field types", async () => {
          const client = new AuthClient(request);
          const response = await client.signup(payload);
          await attachExchange("POST", "/auth/signup", payload, response);
          await allure.step(`Expect ${expected}`, async () => {
            expect(response.status()).toBe(expected);
          });
        });
      });
    }
  });

  test.describe("POST /auth/login", () => {
    const feature = "Login";

    test("should_return_200_with_bearer_token_when_credentials_valid", async ({
      request,
    }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Login returns access_token and token_type bearer");
      await allure.severity("critical");

      const payload: LoginPayload = {
        email: seedEmail,
        password: SEED_PASSWORD,
        remember_me: false,
      };

      await allure.step("POST /auth/login", async () => {
        const client = new AuthClient(request);
        const response = await client.login(payload);
        await attachExchange("POST", "/auth/login", payload, response);

        await allure.step("Expect 200 OK", async () => {
          expect(response.status()).toBe(HTTP.OK);
        });

        await allure.step("Expect token payload", async () => {
          const body = await readEnvelope(response);
          expect(body.access_token).toBeTruthy();
          expect(body.token_type).toBe("bearer");
          expect(body.role).toBeTruthy();
          expect(body.user).toBeDefined();
          const u = body.user as Record<string, unknown>;
          expect(u).toHaveProperty("user_id");
          expect(u).toHaveProperty("email");
        });
      });
    });

    test("should_return_401_when_password_wrong", async ({ request }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Invalid password — generic error message");
      await allure.severity("critical");

      const payload: LoginPayload = {
        email: seedEmail,
        password: "WrongP@ss999!",
        remember_me: false,
      };

      await allure.step("POST /auth/login with wrong password", async () => {
        const client = new AuthClient(request);
        const response = await client.login(payload);
        await attachExchange("POST", "/auth/login", payload, response);

        await allure.step("Expect 401 Unauthorized", async () => {
          expect(response.status()).toBe(HTTP.UNAUTHORIZED);
        });

        await allure.step("Expect global exception envelope", async () => {
          const body = await readEnvelope(response);
          expect(body.error).toBe("Invalid email or password");
          expect(body.error_code).toBe("AUTH_INVALID_CREDENTIALS");
        });
      });
    });

    test("should_return_401_when_email_not_registered", async ({ request }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Unknown email — same error as wrong password");
      await allure.severity("critical");

      const payload: LoginPayload = {
        email: `no-user-${Date.now()}@example.com`,
        password: "SecureP@ss123",
        remember_me: false,
      };

      await allure.step("POST /auth/login with nonexistent email", async () => {
        const client = new AuthClient(request);
        const response = await client.login(payload);
        await attachExchange("POST", "/auth/login", payload, response);

        await allure.step("Expect 401", async () => {
          expect(response.status()).toBe(HTTP.UNAUTHORIZED);
        });

        await allure.step("Expect identical auth error", async () => {
          const body = await readEnvelope(response);
          expect(body.error).toBe("Invalid email or password");
        });
      });
    });

    for (const row of authData.invalid.login_missing_fields as InvalidRow[]) {
      test(`should_return_expected_status_when_${row.case}`, async ({
        request,
      }) => {
        await allure.epic("Auth");
        await allure.feature(feature);
        await allure.story(`Login validation: ${row.case}`);
        await allure.severity("normal");
        await allure.parameter("case", row.case);
        if (row.note) {
          await allure.parameter("note", row.note);
        }

        const expected =
          row.expected_status ?? HTTP.UNPROCESSABLE;
        const payload = row.data as unknown as LoginPayload;

        await allure.step("POST /auth/login with incomplete body", async () => {
          const client = new AuthClient(request);
          const response = await client.login(payload);
          await attachExchange("POST", "/auth/login", payload, response);
          await allure.step(`Expect HTTP ${expected}`, async () => {
            expect(response.status()).toBe(expected);
          });
        });
      });
    }
  });

  test.describe("GET /auth/me", () => {
    const feature = "Session / profile";

    test("should_return_200_profile_when_bearer_token_valid", async ({
      request,
    }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("JWT bearer returns UserProfileResponse");
      await allure.severity("critical");

      const signupPayload: SignupPayload = {
        ...authData.valid.signup,
        email: `me.${Date.now()}@example.com`,
        role: authData.valid.signup.role as SignupPayload["role"],
      };

      await allure.step("Create user via signup", async () => {
        const ac = new AuthClient(request);
        const signupRes = await ac.signup(signupPayload);
        await attachExchange("POST", "/auth/signup", signupPayload, signupRes);
        await allure.step("Expect signup 201", async () => {
          expect(signupRes.status()).toBe(HTTP.CREATED);
        });

        const signedUp = await readEnvelope(signupRes);
        const u = signedUp.user as Record<string, unknown> | undefined;
        if (u?.user_id) {
          createdUserIds.push(String(u.user_id));
        }
        const token = signedUp.access_token as string | undefined;
        expect(token).toBeTruthy();

        await allure.step("GET /auth/me with Bearer", async () => {
          const client = new AuthClient(request, token);
          const meRes = await client.me();
          await attachExchange(
            "GET",
            "/auth/me",
            { Authorization: "Bearer ***" },
            meRes,
          );

          await allure.step("Expect 200", async () => {
            expect(meRes.status()).toBe(HTTP.OK);
          });

          await allure.step("Expect UserProfileResponse core fields", async () => {
            const profile = await readEnvelope(meRes);
            expect(profile.user_id).toBeTruthy();
            expect(profile.email).toBe(signupPayload.email);
            expect(profile.full_name).toBe(signupPayload.full_name);
            expect(profile.role).toBe(signupPayload.role);
          });
        });
      });
    });

    test("should_fail_when_authorization_header_missing", async ({
      playwright,
    }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Missing Authorization — global 401 envelope");
      await allure.severity("normal");

      await allure.step("GET /auth/me without Authorization", async () => {
        await attachRequest("GET", "/auth/me", undefined);
        // Isolated context: default `request` shares cookies/storage with prior
        // tests in this file (signup/login), which can incorrectly return 200.
        const baseURL = process.env.BASE_URL ?? "http://127.0.0.1:8000";
        const isolated = await playwright.request.newContext({
          baseURL,
          extraHTTPHeaders: {
            Accept: "application/json",
          },
        });
        let responseStatus = 0;
        let text = "";
        try {
          const response = await isolated.get("/auth/me");
          text = await response.text();
          responseStatus = response.status();
          await attachResponse(responseStatus, text);
          await allure.attachment(
            "exchange-GET-_auth_me",
            JSON.stringify(
              {
                method: "GET",
                path: "/auth/me",
                request: null,
                status: responseStatus,
                responseBody: text,
              },
              null,
              2,
            ),
            ContentType.JSON,
          );

          await allure.step("Expect 401 from application handlers", async () => {
            expect(responseStatus).toBe(HTTP.UNAUTHORIZED);
          });
          await allure.step("Expect Not authenticated", async () => {
            const body = JSON.parse(text) as Record<string, unknown>;
            expect(body.error).toBe("Not authenticated");
          });
        } finally {
          await isolated.dispose();
        }
      });
    });
  });

  test.describe("POST /auth/forgot-password", () => {
    const feature = "Password reset";

    test("should_return_200_for_registered_email", async ({ request }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("Forgot password — generic success message");
      await allure.severity("normal");

      const body = { email: seedEmail };

      await allure.step("POST /auth/forgot-password", async () => {
        const client = new AuthClient(request);
        const response = await client.forgotPassword(body);
        await attachExchange("POST", "/auth/forgot-password", body, response);

        await allure.step("Expect 200", async () => {
          expect(response.status()).toBe(HTTP.OK);
        });

        await allure.step("Expect ForgotPasswordResponse message", async () => {
          const json = await readEnvelope(response);
          expect(json.message).toBe(
            "If the email exists, a password reset link has been sent",
          );
        });
      });
    });

    test("should_return_200_for_nonexistent_email_same_message", async ({
      request,
    }) => {
      await allure.epic("Auth");
      await allure.feature(feature);
      await allure.story("No email enumeration — same response body");
      await allure.severity("normal");

      const body = { email: `ghost-${Date.now()}@example.com` };

      await allure.step("POST /auth/forgot-password unknown email", async () => {
        const client = new AuthClient(request);
        const response = await client.forgotPassword(body);
        await attachExchange("POST", "/auth/forgot-password", body, response);

        await allure.step("Expect 200", async () => {
          expect(response.status()).toBe(HTTP.OK);
        });

        await allure.step("Expect identical generic message", async () => {
          const json = await readEnvelope(response);
          expect(json.message).toBe(
            "If the email exists, a password reset link has been sent",
          );
        });
      });
    });
  });
});
