import { test, expect } from '@playwright/test';

// Test interview session ID and token generated for this environment
const SESSION_ID = '190';
const TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxOTAiLCJyb2xlIjoiaW50ZXJ2aWV3IiwiZXhwIjoxNzc4ODYxOTg1fQ.LhDRbA8G9uLFrSJj_GfbSuoUkVK3g_txBOM9K2So2EM';
const INTERVIEW_URL = `/interview/live/${SESSION_ID}?token=${TOKEN}`;

test.use({
  // Emulate camera and microphone for the hardware check
  launchOptions: {
    args: [
      '--use-fake-ui-for-media-stream',
      '--use-fake-device-for-media-stream',
      '--mute-audio'
    ],
  },
  permissions: ['camera', 'microphone'],
});

test.describe('Expert Assessment - Interview Flow', () => {
  test.describe.configure({ mode: 'serial' });
  
  test('should load the interview board directly', async ({ page }) => {
    test.setTimeout(120000); // 2 minutes for full AI cycle
    // 1. Navigate to the interview page
    console.log('Navigating to:', INTERVIEW_URL);
    await page.goto(INTERVIEW_URL, { waitUntil: 'networkidle' });

    // 2. Verify main Interview Interface (Classic Board) loads immediately
    try {
        await expect(page.getByText(/Assessment Board/i)).toBeVisible({ timeout: 30000 });
        console.log('Assessment board loaded successfully.');
    } catch (e) {
        console.error('Assessment board failed to load. Capturing screenshot...');
        await page.screenshot({ path: 'test-results/assessment-board-failure.png' });
        // Re-throw to fail the test
        throw e;
    }

    // 3. Submit an answer
    const textarea = page.locator('textarea');
    await expect(textarea).toBeVisible({ timeout: 15000 });
    await textarea.fill('Testing Playwright E2E Integration.');
    
    await page.getByRole('button', { name: /Submit/i }).click();

    // 4. Verify Feedback
    await expect(page.getByText(/AI Evaluation/i)).toBeVisible({ timeout: 60000 });
    console.log('Feedback received.');
  });

  test('should handle "Return Home" redirection correctly on termination', async ({ page }) => {
    await page.goto(INTERVIEW_URL);
    
    // Wait for Assessment Board to load
    await expect(page.getByText(/Assessment Board/i)).toBeVisible({ timeout: 30000 });

    // 5. Wait for grace period to expire, then simulate security violations
    console.log('Waiting for grace period to expire (10s)...');
    await page.waitForTimeout(11000);
    console.log('Simulating security violations...');
    for (let i = 0; i < 3; i++) {
        await page.evaluate(() => {
            window.dispatchEvent(new Event('visibilitychange'));
            // Trigger focus loss multiple times
            Object.defineProperty(document, 'hidden', { value: true, writable: true });
            document.dispatchEvent(new Event('visibilitychange'));
        });
        await page.waitForTimeout(1000);
    }

    await expect(page.getByText(/Session Terminated/i)).toBeVisible({ timeout: 15000 });
    console.log('Session terminated as expected.');

    await page.getByRole('button', { name: /Return Home/i }).click();

    // Verify redirection to /calrims/
    await expect(page).toHaveURL(/\/calrims\/$/, { timeout: 15000 });
    console.log('Redirection verified.');
  });
});
