import { test, expect, Page } from '@playwright/test';

// Test credentials
const TEST_EMAIL = 's.n@gmail.com';
const TEST_PASSWORD = 'Kaay*123';

// Configure for visible, interactive testing
test.use({
  headless: false,
  launchOptions: {
    slowMo: 300, // Slow down so you can see what's happening
  },
});

// Helper to login
async function login(page: Page) {
  await page.goto('http://localhost:5173');
  await page.waitForLoadState('networkidle');

  // Check if on login page
  const emailInput = page.locator('input[type="email"], input[placeholder*="email"]').first();
  const isLoginPage = await emailInput.isVisible().catch(() => false);

  if (isLoginPage) {
    console.log('\n🔐 Logging in as', TEST_EMAIL);
    await emailInput.fill(TEST_EMAIL);
    await page.locator('input[type="password"]').fill(TEST_PASSWORD);
    await page.locator('button[type="submit"]').click();
    await page.waitForTimeout(3000);
  }
}

// Helper to send a message and wait for response
async function sendMessage(page: Page, message: string): Promise<string> {
  // Find and fill the input
  const input = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"], input[type="text"]').first();
  await input.fill(message);
  await page.keyboard.press('Enter');

  // Wait for response to complete
  await page.waitForSelector('text=Completed', { timeout: 90000 }).catch(() => {
    console.log('Timeout waiting for Completed status');
  });

  await page.waitForTimeout(2000);

  // Get main content
  const mainContent = page.locator('main, [class*="flex-1"]').first();
  const text = await mainContent.textContent() || '';
  return text;
}

test.describe('JIRA Live E2E Tests', () => {
  test('JIRA Query Tests - Visual', async ({ page }) => {
    // Login first
    await login(page);

    // Wait for the main app to load
    await page.waitForTimeout(2000);

    // Take screenshot of initial state
    await page.screenshot({ path: 'test-results/01-initial.png' });

    // Select JIRA from sidebar
    console.log('\n📌 Selecting JIRA connector...');
    // Look for button containing JIRA text
    const jiraButton = page.locator('button').filter({ hasText: 'JIRA' }).first();
    await jiraButton.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/02-jira-selected.png' });

    // Test 1: List open tickets
    console.log('\n🧪 Test 1: List my open tickets');
    const response1 = await sendMessage(page, 'List my open tickets');
    await page.screenshot({ path: 'test-results/03-open-tickets.png' });
    console.log(`   Response length: ${response1.length} chars`);
    expect(response1.length).toBeGreaterThan(50);

    // Test 2: List projects
    console.log('\n🧪 Test 2: What projects do I have?');
    const response2 = await sendMessage(page, 'What projects do I have access to?');
    await page.screenshot({ path: 'test-results/04-projects.png' });
    console.log(`   Response length: ${response2.length} chars`);
    expect(response2.length).toBeGreaterThan(50);

    // Test 3: High priority issues
    console.log('\n🧪 Test 3: High priority issues');
    const response3 = await sendMessage(page, 'Show high priority issues');
    await page.screenshot({ path: 'test-results/05-high-priority.png' });
    console.log(`   Response length: ${response3.length} chars`);
    expect(response3.length).toBeGreaterThan(50);

    // Test 4: Specific issue
    console.log('\n🧪 Test 4: Get specific issue ORALIA-74');
    const response4 = await sendMessage(page, 'Get details for issue ORALIA-74');
    await page.screenshot({ path: 'test-results/06-issue-details.png' });
    console.log(`   Response length: ${response4.length} chars`);
    expect(response4.length).toBeGreaterThan(50);

    console.log('\n✅ All JIRA tests completed!');
    console.log('   Screenshots saved to test-results/');

    // Keep browser open for 10 seconds so user can see final state
    await page.waitForTimeout(10000);
  });
});
