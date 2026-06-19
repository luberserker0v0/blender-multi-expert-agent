import { test, expect } from '@playwright/test';
import { mockBridgeApi, createMockActivityWebSocket } from './helpers';

test.beforeEach(async ({ page }) => {
  await mockBridgeApi(page);
  const mockWs = createMockActivityWebSocket(page);
  await mockWs.setup();
});

test.describe('UI Load', () => {
  test('page loads without console errors', async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });

    await page.goto('/');
    await expect(page.getByText('Current Session')).toBeVisible();
    expect(errors).toHaveLength(0);

    const screenshotPath = testInfo.outputPath('01-page-load.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('page-load', { path: screenshotPath });
  });

  test('Composer renders with stage chips visible', async ({ page }, testInfo) => {
    await page.goto('/');
    await expect(page.getByText('stage: idle')).toBeVisible();
    await expect(page.getByText('workflow: idle')).toBeVisible();

    const screenshotPath = testInfo.outputPath('02-composer-chips.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('composer-chips', { path: screenshotPath });
  });

  test('ActivityFeed renders empty state skeleton', async ({ page }, testInfo) => {
    await page.goto('/');
    await expect(page.getByText('Conversation Surface')).toBeVisible();
    await expect(page.getByText(/messages/)).toBeVisible();

    const screenshotPath = testInfo.outputPath('03-activity-feed-skeleton.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('activity-feed-skeleton', { path: screenshotPath });
  });

  test('Settings panel opens on click', async ({ page }, testInfo) => {
    await page.goto('/');
    await page.locator('aside').getByRole('button', { name: 'Settings' }).click();
    await expect(page.getByText('Environment Defaults')).toBeVisible();

    const screenshotPath = testInfo.outputPath('04-settings-panel.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('settings-panel', { path: screenshotPath });
  });
});
