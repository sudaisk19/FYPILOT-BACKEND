import type { APIRequestContext } from "@playwright/test";

import { BaseClient, type CachedApiResponse } from "./base.client";

/** Mirrors app/schemas/user.py UserCreate and app/schemas/auth_schema.py login. */
export interface SignupPayload {
  full_name: string;
  email: string;
  password: string;
  role: "student" | "faculty" | "admin";
}

export interface LoginPayload {
  email: string;
  password: string;
  remember_me?: boolean;
}

export class AuthClient extends BaseClient {
  constructor(request: APIRequestContext, token?: string) {
    super(request, token);
  }

  signup(payload: SignupPayload): Promise<CachedApiResponse> {
    return this.post("/auth/signup", { data: payload });
  }

  login(payload: LoginPayload): Promise<CachedApiResponse> {
    return this.post("/auth/login", { data: payload });
  }

  logout(): Promise<CachedApiResponse> {
    return this.post("/auth/logout");
  }

  me(): Promise<CachedApiResponse> {
    return this.get("/auth/me");
  }

  forgotPassword(payload: { email: string }): Promise<CachedApiResponse> {
    return this.post("/auth/forgot-password", { data: payload });
  }

  resetPassword(payload: {
    token: string;
    new_password: string;
    confirm_password: string;
  }): Promise<CachedApiResponse> {
    return this.post("/auth/reset-password", { data: payload });
  }

  /**
   * No public `DELETE /users/:id` exists in the current HTTP layer; keep hooks
   * stable until an admin cleanup endpoint is available.
   */
  async deleteTestUser(_userId: string): Promise<void> {
    void _userId;
  }
}
