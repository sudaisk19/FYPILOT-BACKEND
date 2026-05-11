import * as path from "path";

import { defineConfig } from "@playwright/test";
import dotenv from "dotenv";

dotenv.config({ path: path.resolve(__dirname, ".env") });

export default defineConfig({
  testDir: "./tests",
  timeout: 30000,
  retries: 0,
  fullyParallel: false,
  workers: 1,
  globalTeardown: "./global-teardown.ts",
  use: {
    baseURL: process.env.BASE_URL ?? "http://127.0.0.1:8000",
    extraHTTPHeaders: {
      Accept: "application/json",
    },
  },
  reporter: [
    ["list"],
    [
      "allure-playwright",
      {
        detail: true,
        outputFolder: "allure-results",
        suiteTitle: true,
        environmentInfo: {
          framework: "Playwright",
          language: "TypeScript",
          environment: process.env.NODE_ENV || "test",
          base_url: process.env.BASE_URL || "http://localhost:8000",
        },
      },
    ],
  ],
});
