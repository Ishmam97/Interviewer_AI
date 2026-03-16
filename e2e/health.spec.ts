/**
 * Smoke test — confirms the frontend loads and the backend is reachable.
 * Runs against a live stack (docker compose up).
 */

import { test, expect } from "@playwright/test";

const API = process.env.API_BASE_URL || "http://localhost:8000";

test("frontend loads without JS errors", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));

  await page.goto("/");
  await expect(page).toHaveTitle(/.+/); // any non-empty title
  expect(errors).toHaveLength(0);
});

test("backend health endpoint returns healthy", async ({ request }) => {
  const r = await request.get(`${API}/health`);
  expect(r.ok()).toBe(true);
  const body = await r.json();
  expect(body.status).toBe("healthy");
});
