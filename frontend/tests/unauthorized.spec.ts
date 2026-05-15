import { test, expect } from '@playwright/test';

test.describe('Security - Unauthorized Access', () => {
    test('should redirect to login when accessing dashboard without session', async ({ page }) => {
        // Ensure no session exists
        await page.goto('/');
        await page.evaluate(() => localStorage.clear());
        
        // Attempt to access a protected application details page
        // Use a dummy ID
        await page.goto('/dashboard/hr/applications/1');

        // It should either show the loading spinner then redirect, or redirect immediately
        // The current layout.tsx redirects to /auth/login?expired=true
        await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15000 });
        console.log('Redirected to login as expected.');
    });
});
