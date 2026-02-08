import { test, expect } from '@playwright/test';

test('app loads and shows login page', async ({ page }) => {
  await page.goto('/');

  // Should redirect to login or show main app
  const pageContent = await page.content();
  console.log('Page loaded, URL:', page.url());

  // Take a screenshot
  await page.screenshot({ path: 'test-results/initial-load.png' });

  // Check if we see login or main app
  const hasLogin = await page.locator('text=Sign in, text=Login, input[type="email"]').first().isVisible().catch(() => false);
  const hasMosaic = await page.locator('text=Mosaic').first().isVisible().catch(() => false);

  console.log('Has login form:', hasLogin);
  console.log('Has Mosaic branding:', hasMosaic);

  expect(hasLogin || hasMosaic).toBe(true);
});

test('login page elements', async ({ page }) => {
  await page.goto('/login');
  await page.waitForLoadState('networkidle');

  await page.screenshot({ path: 'test-results/login-page.png' });

  // Check for login form elements
  const emailInput = page.locator('input[type="email"], input[name="email"], input[placeholder*="email" i]');
  const passwordInput = page.locator('input[type="password"]');
  const submitButton = page.locator('button[type="submit"], button:has-text("Sign"), button:has-text("Log")');

  console.log('Email input visible:', await emailInput.isVisible().catch(() => false));
  console.log('Password input visible:', await passwordInput.isVisible().catch(() => false));
  console.log('Submit button visible:', await submitButton.isVisible().catch(() => false));
});
