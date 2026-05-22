import { test, expect } from '@playwright/test';

test.describe('Authentication Flow', () => {
  test('Should block weak passwords and enforce Terms of Service agreement during registration', async ({ page }) => {
    // Use the full basePath URL since Next.js redirects /auth/register -> /calrims/auth/register/
    await page.goto('/calrims/auth/register/');

    // Wait for page to fully load
    await page.waitForLoadState('networkidle');

    const submitButton = page.locator('button:has-text("Create Account")');
    
    // 1. Initial State: Button should be disabled (empty inputs)
    await expect(submitButton).toBeDisabled();

    // 2. Fill weak password: Strength meter should be Weak, button disabled
    await page.fill('input[type="email"]', 'automated_test@domain.com');
    await page.fill('input#password', 'weak');
    await page.fill('input#confirmPassword', 'weak');
    
    const weakMeter = page.locator('text=Weak');
    await expect(weakMeter).toBeVisible({ timeout: 5000 });
    await expect(submitButton).toBeDisabled();

    // 3. Fill strong password but leave Terms unchecked: Button should still be disabled
    await page.fill('input#password', 'StrongPass123!');
    await page.fill('input#confirmPassword', 'StrongPass123!');
    
    const strongMeter = page.locator('text=Strong');
    await expect(strongMeter).toBeVisible({ timeout: 5000 });
    await expect(submitButton).toBeDisabled(); // disabled because Terms not checked

    // 4. Click the Terms checkbox: Button should become enabled
    await page.click('#terms-checkbox');
    await expect(submitButton).toBeEnabled();
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
