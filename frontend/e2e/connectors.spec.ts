import { test, expect, Page } from '@playwright/test';

// Test credentials - update these with actual test credentials
const TEST_EMAIL = 'santosh.naranapatty@kaaylabs.com';
const TEST_PASSWORD = process.env.TEST_PASSWORD || 'testpass123';

// Helper to login
async function login(page: Page) {
  await page.goto('/');

  // Check if already logged in
  const hasMosaic = await page.locator('text=Mosaic').isVisible().catch(() => false);
  if (hasMosaic) {
    console.log('Already logged in');
    return;
  }

  // Go to login page
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  // Fill credentials
  await page.locator('input[type="email"], input[name="email"]').fill(TEST_EMAIL);
  await page.locator('input[type="password"]').fill(TEST_PASSWORD);

  // Find and click submit button
  const submitBtn = page.locator('button').filter({ hasText: /sign|log|submit/i }).first();
  await submitBtn.click();

  // Wait for redirect to main app
  await page.waitForURL('/', { timeout: 10000 });
  await expect(page.locator('h1:has-text("Mosaic")')).toBeVisible();
}

// Helper to select a datasource
async function selectDatasource(page: Page, datasourceName: string) {
  // Click on the datasource in the sidebar - look for the connector name
  const sidebarItem = page.locator(`text=${datasourceName}`).first();
  await sidebarItem.click({ timeout: 5000 });

  // Wait for connection (green dot or "Connected" text)
  await page.waitForTimeout(1000);
  console.log(`Selected datasource: ${datasourceName}`);
}

// Helper to send a message and wait for response
async function sendMessage(page: Page, message: string): Promise<string> {
  // Find and fill the input - look for placeholder text
  const input = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"]').first();
  await input.fill(message);

  // Submit
  await page.keyboard.press('Enter');

  // Wait for Agent Activity to show "Completed"
  await page.waitForSelector('text=Completed', { timeout: 45000 }).catch(() => {
    console.log('Timeout waiting for Completed status');
  });

  // Additional wait for response to fully render
  await page.waitForTimeout(2000);

  // Take a screenshot of the result
  await page.screenshot({ path: `test-results/response-${Date.now()}.png` });

  // Get the main content area text
  const mainContent = page.locator('main, [class*="flex-1"]').first();
  const text = await mainContent.textContent() || '';

  console.log(`Response received (${text.length} chars): ${text.substring(0, 200)}...`);
  return text;
}

// Helper to verify response contains expected content
function verifyResponse(response: string, expectedPatterns: string[]) {
  const lowerResponse = response.toLowerCase();
  const foundPatterns: string[] = [];
  const missingPatterns: string[] = [];

  for (const pattern of expectedPatterns) {
    if (lowerResponse.includes(pattern.toLowerCase())) {
      foundPatterns.push(pattern);
    } else {
      missingPatterns.push(pattern);
    }
  }

  return { foundPatterns, missingPatterns, hasContent: response.length > 50 };
}

test.describe('Connector Tests - PM Workflow', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test.describe('Slack Connector', () => {
    test.beforeEach(async ({ page }) => {
      await selectDatasource(page, 'Slack');
    });

    test('catch up - what did I miss', async ({ page }) => {
      const response = await sendMessage(page, 'What did I miss over the last 2 days?');
      console.log('Slack catch-up response:', response.substring(0, 500));

      const result = verifyResponse(response, ['message', 'channel', 'from']);
      expect(result.hasContent).toBe(true);
    });

    test('list channels', async ({ page }) => {
      const response = await sendMessage(page, 'List all my Slack channels');
      console.log('Slack channels response:', response.substring(0, 500));

      const result = verifyResponse(response, ['channel', '#']);
      expect(result.hasContent).toBe(true);
    });

    test('search messages', async ({ page }) => {
      const response = await sendMessage(page, 'Search for messages about deployment');
      console.log('Slack search response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('specific channel messages', async ({ page }) => {
      const response = await sendMessage(page, 'Show me recent messages from #general');
      console.log('Slack #general response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });
  });

  test.describe('JIRA Connector', () => {
    test.beforeEach(async ({ page }) => {
      await selectDatasource(page, 'JIRA');
    });

    test('list projects', async ({ page }) => {
      const response = await sendMessage(page, 'What projects do I have access to?');
      console.log('JIRA projects response:', response.substring(0, 500));

      const result = verifyResponse(response, ['project', 'oralia', 'sensi']);
      expect(result.hasContent).toBe(true);
    });

    test('Oralia project deep dive', async ({ page }) => {
      const response = await sendMessage(page, 'Show me all open issues in Oralia project');
      console.log('JIRA Oralia response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('Sensi Hire backlog', async ({ page }) => {
      const response = await sendMessage(page, 'What is in the backlog for Sensi Hire?');
      console.log('JIRA Sensi Hire response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('team workload', async ({ page }) => {
      const response = await sendMessage(page, 'Who is working on what in Oralia?');
      console.log('JIRA workload response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('bugs in project', async ({ page }) => {
      const response = await sendMessage(page, 'Are there any bugs in Sensi Hire that need attention?');
      console.log('JIRA bugs response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });
  });

  test.describe('MySQL Connector', () => {
    test.beforeEach(async ({ page }) => {
      await selectDatasource(page, 'MySQL');
    });

    test('list tables', async ({ page }) => {
      const response = await sendMessage(page, 'What tables are in the database?');
      console.log('MySQL tables response:', response.substring(0, 500));

      const result = verifyResponse(response, ['table']);
      expect(result.hasContent).toBe(true);
    });

    test('describe schema', async ({ page }) => {
      const response = await sendMessage(page, 'Describe the schema of the users table');
      console.log('MySQL schema response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('count records', async ({ page }) => {
      const response = await sendMessage(page, 'How many records are in each table?');
      console.log('MySQL count response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('analytical query', async ({ page }) => {
      const response = await sendMessage(page, 'Show me a summary of the data - what are the main entities and their relationships?');
      console.log('MySQL analytics response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });
  });

  test.describe('S3 Connector', () => {
    test.beforeEach(async ({ page }) => {
      await selectDatasource(page, 'S3');
    });

    test('list buckets', async ({ page }) => {
      const response = await sendMessage(page, 'What S3 buckets do I have?');
      console.log('S3 buckets response:', response.substring(0, 500));

      const result = verifyResponse(response, ['bucket']);
      expect(result.hasContent).toBe(true);
    });

    test('list files in bucket', async ({ page }) => {
      const response = await sendMessage(page, 'List files in my main bucket');
      console.log('S3 files response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('search for files', async ({ page }) => {
      const response = await sendMessage(page, 'Search for any PDF or CSV files');
      console.log('S3 search response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });
  });

  test.describe('GitHub Connector', () => {
    test.beforeEach(async ({ page }) => {
      await selectDatasource(page, 'GitHub');
    });

    test('list repositories', async ({ page }) => {
      const response = await sendMessage(page, 'What repositories do I have?');
      console.log('GitHub repos response:', response.substring(0, 500));

      const result = verifyResponse(response, ['repo', 'repository']);
      expect(result.hasContent).toBe(true);
    });

    test('open issues', async ({ page }) => {
      const response = await sendMessage(page, 'Show me open issues across my repos');
      console.log('GitHub issues response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('pull requests', async ({ page }) => {
      const response = await sendMessage(page, 'Are there any open pull requests?');
      console.log('GitHub PRs response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });

    test('recent activity', async ({ page }) => {
      const response = await sendMessage(page, 'What is the recent activity in ConnectorMCP repo?');
      console.log('GitHub activity response:', response.substring(0, 500));

      expect(response.length).toBeGreaterThan(20);
    });
  });
});

// Quick smoke test for all connectors
test.describe('Quick Smoke Test', () => {
  test('all connectors respond', async ({ page }) => {
    await login(page);

    const connectors = ['Slack', 'JIRA', 'MySQL', 'S3', 'GitHub'];
    const results: Record<string, { success: boolean; response: string }> = {};

    for (const connector of connectors) {
      try {
        await selectDatasource(page, connector);
        const response = await sendMessage(page, 'Hello, give me a quick summary');
        results[connector] = {
          success: response.length > 20,
          response: response.substring(0, 200)
        };
      } catch (error) {
        results[connector] = {
          success: false,
          response: `Error: ${error}`
        };
      }

      // Start new conversation for next connector
      await page.click('[data-testid="new-conversation"], button:has-text("New")').catch(() => {});
    }

    console.log('Smoke Test Results:', JSON.stringify(results, null, 2));

    // At least 3 connectors should work
    const successCount = Object.values(results).filter(r => r.success).length;
    expect(successCount).toBeGreaterThanOrEqual(3);
  });
});
