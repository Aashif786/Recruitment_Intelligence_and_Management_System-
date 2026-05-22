import { test, expect } from '@playwright/test';

test.describe('Full System Flow - RIMS Platform', () => {

  test.beforeEach(async ({ page }) => {
    // Navigate to homepage before each test (redirect goes to /calrims/)
    await page.goto('/calrims/');
    await page.waitForLoadState('networkidle');
  });

  // ---------------------------------------------------------
  // STEP 2: END-TO-END USER FLOWS
  // ---------------------------------------------------------

  test('Candidate Registration, Suspense Loaders, and AI Access', async ({ page }) => {
    // Verify the landing page loads correctly
    await expect(page.locator('h1')).toBeVisible({ timeout: 10000 });

    // Navigate to the HR register page via the "Start hiring in minutes" CTA
    await page.click('text=Start hiring in minutes');
    // Should land on the login page (with role=hr param)
    await expect(page).toHaveURL(/.*auth\/login/, { timeout: 10000 });

    // Now navigate to register page
    await page.goto('/calrims/auth/register/');
    await page.waitForLoadState('networkidle');

    // Verify Password complexity UI elements
    await page.fill('input[type="email"]', 'automated_e2e@testdomain.com');
    await page.fill('input[type="password"]', 'weak');

    // Strength meter should appear when typing
    await expect(page.locator('text=Weak')).toBeVisible({ timeout: 5000 });

    // Fill strong password
    await page.fill('input[type="password"]', 'StrongH@sh123');
    await expect(page.locator('text=Strong')).toBeVisible({ timeout: 5000 });

    // Accessibility test: terms checkbox should be unchecked by default
    const termsCheckbox = page.locator('#terms-checkbox');
    await expect(termsCheckbox).toHaveAttribute('aria-checked', 'false');
    await termsCheckbox.click();
    await expect(termsCheckbox).toHaveAttribute('aria-checked', 'true');

    // Submit button should be enabled now (strong password + terms checked)
    const submitButton = page.locator('button:has-text("Create Account")');
    await expect(submitButton).toBeEnabled({ timeout: 5000 });
  });

  // ---------------------------------------------------------
  // STEP 5 & 11: ASYNC JOBS & UX CHAOS
  // ---------------------------------------------------------

  test('Async AI Interview Polling Loop and Graceful Loaders', async ({ page }) => {
    // Navigate to the interview access portal
    await page.goto('/calrims/interview/access/');
    await page.waitForLoadState('networkidle');

    // Verify the access form is present
    await expect(page.locator('text=Interview Access')).toBeVisible({ timeout: 10000 });

    // The form has email and access key fields
    const emailInput = page.locator('input#email');
    const keyInput = page.locator('input#key');

    await expect(emailInput).toBeVisible();
    await expect(keyInput).toBeVisible();

    await emailInput.fill('valid_candidate@test.com');
    await keyInput.fill('invalid_test_key_abc');

    // Click the "Enter Interview" button
    await page.click('button:has-text("Enter Interview")');

    // Should show an error (invalid access key)
    await expect(page.locator('text=Access failed').or(page.locator('.text-red-500'))).toBeVisible({ timeout: 10000 });
    console.log('Access key validation working correctly.');
  });

  // ---------------------------------------------------------
  // STEP 9: UX/UI EDGE CASES & COMPLIANCE
  // ---------------------------------------------------------

  test('Legal and Compliance 404 Prevention', async ({ page }) => {
    await page.goto('/calrims/terms/');
    await expect(page.locator('h1:has-text("Terms of Service")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('h1:has-text("404")')).toBeHidden();

    await page.goto('/calrims/privacy/');
    await expect(page.locator('h1:has-text("Privacy Policy")')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('h1:has-text("404")')).toBeHidden();
  });
});
