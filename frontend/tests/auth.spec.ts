import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test('Should block weak passwords during registration', async ({ page }) => {
    // Use the full basePath URL since Next.js redirects /auth/register -> /calrims/auth/register/
    await page.goto('/calrims/auth/register/');

    // Wait for page to fully load (SWR/settings may take a moment)
    await page.waitForLoadState('networkidle');

    await page.fill('input[type="email"]', 'automated_test@domain.com');
    await page.fill('input[type="password"]', 'weak');

    // The UI should display strength meter as Weak
    const strengthMeter = page.locator('text=Weak');
    await expect(strengthMeter).toBeVisible({ timeout: 5000 });

    // The "Create Account" button should be disabled when password is weak (< 4 criteria)
    const submitButton = page.locator('button:has-text("Create Account")');
    await expect(submitButton).toBeDisabled({ timeout: 5000 });
  });

  test('Should redirect unauthenticated users away from HR dashboard to login', async ({ page }) => {
    // Clear all storage to ensure unauthenticated state
    await page.goto('/calrims/auth/login/');
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });

    // Attempt to access protected HR route without session
    await page.goto('/calrims/dashboard/hr/');

    // The dashboard layout redirects unauthenticated users to /auth/login
    await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15000 });
    console.log('Correctly redirected to login when not authenticated.');
  });
});
