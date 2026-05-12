import type { FullConfig } from "@playwright/test";
import { mkdir, writeFile } from "fs/promises";
import path from "path";

export default async function globalTeardown(_config: FullConfig): Promise<void> {
  const resultsDir = path.resolve(__dirname, "allure-results");
  await mkdir(resultsDir, { recursive: true });

  const baseUrl = process.env.BASE_URL ?? "http://localhost:8000";
  const environment = [
    `BASE_URL=${baseUrl}`,
    "ENVIRONMENT=test",
    "FRAMEWORK=Playwright + TypeScript",
    "MODULES_COVERED=Auth,Student,Faculty,Admin,Jury",
    "TEST_TYPE=API Integration",
  ].join("\n");

  await writeFile(
    path.join(resultsDir, "environment.properties"),
    `${environment}\n`,
    "utf-8",
  );
}
