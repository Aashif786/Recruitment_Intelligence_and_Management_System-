import { defineConfig } from '@playwright/test';

// Minimal Playwright configuration to make relative `page.goto('/')` work.
// The E2E specs assume a base URL is available.
const baseURL =
  process.env.PLAYWRIGHT_BASE_URL ||
  process.env.FRONTEND_URL ||
  process.env.NEXT_PUBLIC_APP_URL ||
  process.env.FRONTEND_BASE_URL ||
  'http://localhost:3000';

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL,
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});

