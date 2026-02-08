import { test, expect, Page } from '@playwright/test';

const TEST_EMAIL = 's.n@gmail.com';
const TEST_PASSWORD = 'Kaay*123';

test.use({
  headless: false,
  launchOptions: {
    slowMo: 300,
  },
});

async function login(page: Page) {
  await page.goto('http://localhost:5173');
  await page.waitForLoadState('networkidle');

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

async function sendMessage(page: Page, message: string): Promise<string> {
  const input = page.locator('input[placeholder*="Ask"], textarea[placeholder*="Ask"], input[type="text"]').first();
  await input.fill(message);
  await page.keyboard.press('Enter');

  await page.waitForSelector('text=Completed', { timeout: 90000 }).catch(() => {
    console.log('Timeout waiting for Completed status');
  });

  await page.waitForTimeout(2000);

  const mainContent = page.locator('main, [class*="flex-1"]').first();
  const text = await mainContent.textContent() || '';
  return text;
}

test.describe('Slack Live E2E Tests', () => {
  test('Slack Query Tests - Visual', async ({ page }) => {
    await login(page);
    await page.waitForTimeout(2000);

    // Select Slack from sidebar
    console.log('\n📌 Selecting Slack connector...');
    const slackButton = page.locator('button').filter({ hasText: 'Slack' }).first();
    await slackButton.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/slack-01-selected.png' });

    // Test 1: List channels
    console.log('\n🧪 Test 1: List my channels');
    const response1 = await sendMessage(page, 'List all my Slack channels');
    await page.screenshot({ path: 'test-results/slack-02-channels.png' });
    console.log(`   Response length: ${response1.length} chars`);
    expect(response1.length).toBeGreaterThan(50);

    // Test 2: Search messages
    console.log('\n🧪 Test 2: Search for messages');
    const response2 = await sendMessage(page, 'Search for messages about deployment or release');
    await page.screenshot({ path: 'test-results/slack-03-search.png' });
    console.log(`   Response length: ${response2.length} chars`);
    expect(response2.length).toBeGreaterThan(50);

    // Test 3: Recent activity
    console.log('\n🧪 Test 3: What did I miss');
    const response3 = await sendMessage(page, 'What did I miss in the last 2 days?');
    await page.screenshot({ path: 'test-results/slack-04-missed.png' });
    console.log(`   Response length: ${response3.length} chars`);
    expect(response3.length).toBeGreaterThan(50);

    // Test 4: Specific channel
    console.log('\n🧪 Test 4: Messages from #general');
    const response4 = await sendMessage(page, 'Show me recent messages from #general');
    await page.screenshot({ path: 'test-results/slack-05-general.png' });
    console.log(`   Response length: ${response4.length} chars`);
    expect(response4.length).toBeGreaterThan(50);

    console.log('\n✅ All Slack tests completed!');
    await page.waitForTimeout(5000);
  });
});
