/**
 * E2E tests for the authentication flow.
 * Requires a running stack with a seeded test account or Firebase emulator.
 *
 * Set env vars:
 *   E2E_TEST_EMAIL    — test user email
 *   E2E_TEST_PASSWORD — test user password
 */

import { test, expect } from "@playwright/test";

const EMAIL = process.env.E2E_TEST_EMAIL || "e2e-test@example.com";
const PASSWORD = process.env.E2E_TEST_PASSWORD || "E2eTestPass123!";

test.describe("Sign-in flow", () => {
  test("shows auth form on first load", async ({ page }) => {
    await page.goto("/");
    // Auth form should be visible (sign-in or sign-up tab)
    await expect(
      page.getByRole("tab", { name: /sign.?in/i }).or(
        page.getByPlaceholder(/email/i)
      )
    ).toBeVisible({ timeout: 10_000 });
  });

  test("shows error on bad credentials", async ({ page }) => {
    await page.goto("/");
    await page.getByPlaceholder(/email/i).fill("bad@example.com");
    await page.getByPlaceholder(/password/i).fill("wrongpassword");
    await page.getByRole("button", { name: /sign.?in/i }).click();

    await expect(
      page.getByText(/invalid|incorrect|failed|error/i)
    ).toBeVisible({ timeout: 10_000 });
  });
});

test.describe("Authenticated flow", () => {
  test.skip(
    !process.env.E2E_TEST_EMAIL,
    "Set E2E_TEST_EMAIL + E2E_TEST_PASSWORD to run authenticated tests"
  );

  test("signs in and reaches dashboard", async ({ page }) => {
    await page.goto("/");
    await page.getByPlaceholder(/email/i).fill(EMAIL);
    await page.getByPlaceholder(/password/i).fill(PASSWORD);
    await page.getByRole("button", { name: /sign.?in/i }).click();

    // After sign-in the dashboard or home section should appear
    await expect(
      page.getByText(/dashboard|interview|welcome/i)
    ).toBeVisible({ timeout: 15_000 });
  });
});
