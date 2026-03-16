import { test, expect, Page } from '@playwright/test';

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:8080';

// Helper: sign in with test credentials
async function signIn(page: Page) {
  await page.goto(BASE_URL);
  await page.fill('[placeholder*="email" i]', process.env.E2E_EMAIL || 'test@example.com');
  await page.fill('[placeholder*="password" i]', process.env.E2E_PASSWORD || 'testpassword');
  await page.click('button[type="submit"], button:has-text("Sign In")');
  await expect(page.locator('text=Start Your Interview')).toBeVisible({ timeout: 10000 });
}

test.describe('Interview Setup', () => {
  test('shows interview setup page after sign-in', async ({ page }) => {
    await signIn(page);
    await expect(page.locator('text=Start Your Interview')).toBeVisible();
    await expect(page.locator('text=Resume')).toBeVisible();
    await expect(page.locator('text=Job Description')).toBeVisible();
  });

  test('shows validation error when starting without files', async ({ page }) => {
    await signIn(page);
    // Try to start without uploading anything
    const startBtn = page.locator('button', { hasText: /Start.*Interview/i });
    await startBtn.click();
    // Should show a toast or alert about missing files
    await expect(page.locator('text=/missing|upload|required/i')).toBeVisible({ timeout: 5000 });
  });

  test('shows validation error when missing interview type', async ({ page }) => {
    await signIn(page);
    // Upload resume via paste tab
    await page.click('text=Paste Text >> nth=0');
    await page.fill('textarea[placeholder*="resume" i]', 'Software engineer with 5 years experience in Python and React.');
    await page.click('button:has-text("Save Resume Content")');
    // Upload JD via paste tab
    await page.click('text=Paste Text >> nth=1');
    await page.fill('textarea[placeholder*="job description" i]', 'Looking for a senior software engineer.');
    await page.click('button:has-text("Save Job Description")');
    // Click start without selecting interview type
    const startBtn = page.locator('button', { hasText: /Start.*Interview/i });
    await startBtn.click();
    await expect(page.locator('text=/interview type/i')).toBeVisible({ timeout: 5000 });
  });

  test('interview type dropdown contains all expected types', async ({ page }) => {
    await signIn(page);
    await page.click('[data-radix-select-trigger]');
    await expect(page.locator('text=Initial Screening')).toBeVisible();
    await expect(page.locator('text=Technical Coding')).toBeVisible();
    await expect(page.locator('text=Behavioral')).toBeVisible();
    await expect(page.locator('text=HR / Culture Fit')).toBeVisible();
  });

  test('resume persists across page reload via localStorage', async ({ page }) => {
    await signIn(page);
    // Paste resume
    await page.click('text=Paste Text >> nth=0');
    await page.fill('textarea[placeholder*="resume" i]', 'My resume content here');
    await page.click('button:has-text("Save Resume Content")');
    await expect(page.locator('text=resume.txt')).toBeVisible();
    // Reload
    await page.reload();
    await expect(page.locator('text=Start Your Interview')).toBeVisible({ timeout: 10000 });
    // Resume should still be shown
    await expect(page.locator('text=resume.txt')).toBeVisible({ timeout: 5000 });
  });
});

test.describe('Interview Flow', () => {
  test.skip('full interview flow reaches live phase', async ({ page }) => {
    // This test requires real API keys — skip in CI without credentials
    await signIn(page);

    await page.click('text=Paste Text >> nth=0');
    await page.fill('textarea[placeholder*="resume" i]', 'Senior software engineer with React and Python experience.');
    await page.click('button:has-text("Save Resume Content")');

    await page.click('text=Paste Text >> nth=1');
    await page.fill('textarea[placeholder*="job description" i]', 'Looking for a senior full-stack engineer.');
    await page.click('button:has-text("Save Job Description")');

    await page.click('[data-radix-select-trigger]');
    await page.click('text=Initial Screening');

    await page.click('button', { hasText: /Start.*Interview/i });

    // Should show preparing state
    await expect(page.locator('text=/uploading|preparing|generating/i')).toBeVisible({ timeout: 5000 });

    // Should eventually reach live interview
    await expect(page.locator('text=/Live/i')).toBeVisible({ timeout: 60000 });
    await expect(page.locator('textarea[placeholder*="answer" i]')).toBeVisible();
  });
});
