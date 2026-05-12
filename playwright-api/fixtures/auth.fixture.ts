import { expect, test as base } from "@playwright/test";

import { AdminClient } from "../api/admin.client";
import { AuthClient } from "../api/auth.client";
import { FacultyClient } from "../api/faculty.client";
import { GroupsClient } from "../api/groups.client";
import { JuryClient } from "../api/jury.client";
import { StudentClient } from "../api/student.client";

export type RoleTokens = {
  student: string;
  supervisor: string;
  jury: string;
  admin: string;
};

/** Populated once per process when role fixtures run (`workers: 1` in config). */
let roleTokenCache: RoleTokens | undefined;

async function loginOnce(
  auth: AuthClient,
  email: string | undefined,
  password: string | undefined,
): Promise<string> {
  if (!email?.trim() || !password) {
    return "";
  }
  const res = await auth.login({
    email: email.trim(),
    password,
    remember_me: false,
  });
  const body = (await res.json()) as { access_token?: string };
  return body.access_token ?? "";
}

/**
 * Worker-scoped tokens plus per-role API clients with Bearer auth applied.
 * Requires credentials in `.env` (see `.env.example`).
 */
export const test = base.extend<{
  roleTokens: RoleTokens;
  studentAPI: StudentClient;
  supervisorAPI: FacultyClient;
  juryAPI: JuryClient;
  adminAPI: AdminClient;
  groupsAPI: GroupsClient;
}>({
  roleTokens: async ({ request }, use) => {
    if (!roleTokenCache) {
      const auth = new AuthClient(request);
      roleTokenCache = {
        student: await loginOnce(
          auth,
          process.env.TEST_AUTH_STUDENT_EMAIL,
          process.env.TEST_AUTH_STUDENT_PASSWORD,
        ),
        supervisor: await loginOnce(
          auth,
          process.env.TEST_AUTH_SUPERVISOR_EMAIL,
          process.env.TEST_AUTH_SUPERVISOR_PASSWORD,
        ),
        jury: await loginOnce(
          auth,
          process.env.TEST_AUTH_JURY_EMAIL,
          process.env.TEST_AUTH_JURY_PASSWORD,
        ),
        admin: await loginOnce(
          auth,
          process.env.TEST_AUTH_ADMIN_EMAIL,
          process.env.TEST_AUTH_ADMIN_PASSWORD,
        ),
      };
    }
    await use(roleTokenCache);
  },

  studentAPI: async ({ request, roleTokens }, use) => {
    const client = new StudentClient(request);
    client.setBearerToken(roleTokens.student);
    await use(client);
  },

  supervisorAPI: async ({ request, roleTokens }, use) => {
    const client = new FacultyClient(request);
    client.setBearerToken(roleTokens.supervisor);
    await use(client);
  },

  juryAPI: async ({ request, roleTokens }, use) => {
    const client = new JuryClient(request);
    client.setBearerToken(roleTokens.jury);
    await use(client);
  },

  adminAPI: async ({ request, roleTokens }, use) => {
    const client = new AdminClient(request);
    client.setBearerToken(roleTokens.admin);
    await use(client);
  },

  groupsAPI: async ({ request, roleTokens }, use) => {
    const client = new GroupsClient(request);
    client.setBearerToken(roleTokens.student);
    await use(client);
  },
});

/** Optional teardown when you need to discard cached tokens between suites. */
export function clearRoleTokenCache(): void {
  roleTokenCache = undefined;
}

export { expect };
