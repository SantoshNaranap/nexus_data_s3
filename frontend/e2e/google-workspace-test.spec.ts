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

  await page.waitForSelector('text=Completed', { timeout: 120000 }).catch(() => {
    console.log('Timeout waiting for Completed status');
  });

  await page.waitForTimeout(2000);

  const mainContent = page.locator('main, [class*="flex-1"]').first();
  const text = await mainContent.textContent() || '';
  return text;
}

test.describe('Google Workspace Live E2E Tests', () => {
  test('Google Workspace Query Tests - Visual', async ({ page }) => {
    await login(page);
    await page.waitForTimeout(2000);

    // Select Google Workspace from sidebar
    console.log('\n📌 Selecting Google Workspace connector...');
    const gwButton = page.locator('button').filter({ hasText: /Google|Workspace|Drive/i }).first();
    await gwButton.click();
    await page.waitForTimeout(1000);
    await page.screenshot({ path: 'test-results/gw-01-selected.png' });

    // Test 1: List Drive files
    console.log('\n🧪 Test 1: List my Drive files');
    const response1 = await sendMessage(page, 'List my recent files in Google Drive');
    await page.screenshot({ path: 'test-results/gw-02-drive-files.png' });
    console.log(`   Response length: ${response1.length} chars`);
    expect(response1.length).toBeGreaterThan(50);

    // Test 2: Calendar
    console.log('\n🧪 Test 2: Calendar today');
    const response2 = await sendMessage(page, "What's on my calendar today?");
    await page.screenshot({ path: 'test-results/gw-03-calendar.png' });
    console.log(`   Response length: ${response2.length} chars`);
    expect(response2.length).toBeGreaterThan(50);

    // Test 3: Search emails
    console.log('\n🧪 Test 3: Recent emails');
    const response3 = await sendMessage(page, 'Show my recent emails');
    await page.screenshot({ path: 'test-results/gw-04-emails.png' });
    console.log(`   Response length: ${response3.length} chars`);
    expect(response3.length).toBeGreaterThan(50);

    console.log('\n✅ All Google Workspace tests completed!');
    await page.waitForTimeout(5000);
  });
});
