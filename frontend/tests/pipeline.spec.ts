import { test, expect } from '@playwright/test';

test.describe('Hiring Pipeline Module', () => {
  test.describe.configure({ mode: 'serial' });
  test.beforeEach(async ({ page }) => {
    // Login as HR
    await page.goto('/calrims/auth/login/');
    await page.fill('input#email', 'hr_automated_test@example.com');
    await page.fill('input#password', 'Password123!');
    await page.click('button[type="submit"]');
    
    // Wait for dashboard to load (allow up to 30s for cookie set + SWR fetch)
    await expect(page).toHaveURL(/.*calrims\/dashboard\/hr/, { timeout: 30000 });
    await page.waitForLoadState('load');

    // Log API responses for debugging
    page.on('response', async response => {
      if (response.url().includes('/api/')) {
        const status = response.status();
        const url = response.url();
        try {
          const body = await response.json();
          console.log(`API Response: ${status} ${url}`, JSON.stringify(body).slice(0, 500));
        } catch (e) {
          console.log(`API Response: ${status} ${url} (not json)`);
        }
      }
    });
  });

  test('Should navigate through the pipeline and perform candidate actions', async ({ page }) => {
    // 1. Navigate to Pipeline Index
    await page.goto('/calrims/dashboard/hr/pipeline');
    await expect(page.locator('h1:has-text("Hiring Pipelines")')).toBeVisible();

    // 2. Search for a job (Optional but good for testing)
    await page.fill('input[placeholder="Search by job title or ID..."]', 'Software');
    
    // 3. Open the first pipeline board (wait for SWR to load jobs)
    const openPipelineButton = page.locator('button:has-text("Open Pipeline")').first();
    await expect(openPipelineButton).toBeVisible({ timeout: 15000 });
    await openPipelineButton.click();
    
    // Wait for the Kanban board to load
    await expect(page).toHaveURL(/.*calrims\/dashboard\/hr\/pipelines\/\d+/, { timeout: 10000 });
    await expect(page.locator('h1:has-text("Pipeline:")')).toBeVisible();

    // 4. Check for candidate cards
    // Wait for at least one card to appear or for the "No data available" text to show
    const candidateCards = page.locator('.min-h-0 .group.animate-in');
    const noDataText = page.locator('text=No data available');
    
    await Promise.race([
      candidateCards.first().waitFor({ state: 'visible', timeout: 15000 }),
      noDataText.first().waitFor({ state: 'visible', timeout: 15000 })
    ]).catch(() => {});

    // Check if we have any candidates
    const count = await candidateCards.count();
    if (count === 0) {
      console.log('No candidates found in pipeline, skipping card interactions.');
      return;
    }

    // 5. Test "Screen" action (Applied -> Screened)
    const appliedColumn = page.locator('div:has(h3:has-text("Applied"))');
    const screenButton = appliedColumn.locator('button:has-text("Screen")').first();
    
    if (await screenButton.isVisible()) {
      await screenButton.click();
      await expect(page.locator('text=Action mark_screened completed')).toBeVisible();
    }

    // 6. Test "Approve" action (Screened -> Interview Scheduled)
    const screenedColumn = page.locator('div:has(h3:has-text("Screened"))');
    const approveButton = screenedColumn.locator('button:has-text("Approve")').first();
    
    if (await approveButton.isVisible()) {
      await approveButton.click();
      await expect(page.locator('text=Action approve_for_interview completed')).toBeVisible();
    }

    // 7. Test "Hire" action (Interview Completed -> Hired)
    // This should redirect to onboarding as per recent changes
    const completedColumn = page.locator('div:has(h3:has-text("Interview Completed"))');
    const hireButton = completedColumn.locator('button:has-text("Hire")').first();
    
    if (await hireButton.isVisible()) {
      await hireButton.click();
      await expect(page.locator('text=Candidate hired! Redirecting to Onboarding...')).toBeVisible();
      // Verify redirect
      await expect(page).toHaveURL(/.*calrims\/dashboard\/onboarding/);
    }
  });

  test('Should perform candidate rejection', async ({ page }) => {
    await page.goto('/calrims/dashboard/hr/pipeline/');
    await page.locator('button:has-text("Open Pipeline")').first().click();

    // Find a card that can be rejected (any card not Hired/Rejected)
    // We use the X icon button
    const rejectButton = page.locator('button:has(svg.lucide-x-circle)').first();
    
    if (await rejectButton.isVisible()) {
      await rejectButton.click();
      
      // Confirm rejection in dialog
      const confirmButton = page.locator('button:has-text("Reject Candidate")');
      await expect(confirmButton).toBeVisible();
      
      // Select a reason if needed (assuming RejectDialog has reasons)
      // For now just click confirm
      await confirmButton.click();
      
      await expect(page.locator('text=Action reject completed')).toBeVisible();
    }
  });

  test('Should handle search filtering and empty states', async ({ page }) => {
    await page.goto('/calrims/dashboard/hr/pipeline');
    await expect(page.locator('h1:has-text("Hiring Pipelines")')).toBeVisible();

    // Search for a non-existent job
    await page.fill('input[placeholder="Search by job title or ID..."]', 'NonExistentJob12345');
    
    // The pipeline index should eventually show no jobs (assuming there's a "no data" or just an empty list)
    // We expect 0 pipeline board cards to be present.
    const openButtons = page.locator('button:has-text("Open Pipeline")');
    await expect(openButtons).toHaveCount(0);

    // Clear search
    await page.fill('input[placeholder="Search by job title or ID..."]', '');
    await expect(openButtons.first()).toBeVisible();
  });

  test('Should support bulk actions and column clearing', async ({ page }) => {
    await page.goto('/calrims/dashboard/hr/pipeline');
    await page.locator('button:has-text("Open Pipeline")').first().click();

    await expect(page.locator('h1:has-text("Pipeline:")')).toBeVisible();
    
    // Check if there are any candidates in the "Applied" or "Rejected" columns
    const column = page.locator('.flex-1.bg-muted').filter({ hasText: 'Rejected' }).first();
    const candidateCards = column.locator('.group.animate-in');
    
    // If we have rejected candidates, try to clear the column
    if (await candidateCards.count() > 0) {
      // Find the clear column button for this specific column
      const clearBtn = column.locator('button[title="Clear Column"]');
      if (await clearBtn.isVisible()) {
        // Setup dialog handler to accept confirmation
        page.once('dialog', dialog => dialog.accept());
        await clearBtn.click();
        
        // Wait for success toast
        await expect(page.locator('text=Successfully deleted')).toBeVisible();
      }
    }
  });

  test('Should handle Review Later flow for completed interviews', async ({ page }) => {
    await page.goto('/calrims/dashboard/hr/pipeline');
    await page.locator('button:has-text("Open Pipeline")').first().click();
    await expect(page.locator('h1:has-text("Pipeline:")')).toBeVisible();

    const completedColumn = page.locator('div:has(h3:has-text("Interview Completed"))');
    const reviewButton = completedColumn.locator('button:has-text("Review")').first();
    
    if (await reviewButton.isVisible()) {
      await reviewButton.click();
      await expect(page.locator('text=Action review_later completed')).toBeVisible();
      
      // Wait for it to appear in Review Later if we had a column for it (optional)
    }
  });
});
