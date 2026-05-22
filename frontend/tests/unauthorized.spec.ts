import { test, expect } from '@playwright/test';

test.describe('Security - Unauthorized Access', () => {
    test('should redirect to login when accessing dashboard without session', async ({ page }) => {
        // Ensure no session exists by navigating to login first and clearing storage
        await page.goto('/calrims/auth/login/');
        await page.evaluate(() => {
            localStorage.clear();
            sessionStorage.clear();
        });

        // Attempt to access a protected application details page
        await page.goto('/calrims/dashboard/hr/applications/1');

        // It should either show the loading spinner then redirect, or redirect immediately
        // The current layout.tsx redirects to /auth/login?expired=true
        await expect(page).toHaveURL(/\/auth\/login/, { timeout: 15000 });
        console.log('Redirected to login as expected.');
    });
});
