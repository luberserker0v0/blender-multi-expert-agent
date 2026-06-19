import { test, expect } from '@playwright/test';
import { mockBridgeApi } from './helpers';

test.describe('Mobile Responsive (gap coverage)', () => {
  test.beforeEach(async ({ page }) => {
    await mockBridgeApi(page);
  });

  test('hamburger menu visible at mobile viewport, sidebar hidden', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    const hamburger = page.locator('button.lg\\:hidden');
    await expect(hamburger).toBeVisible();

    await expect(page.locator('aside')).not.toBeVisible();
  });

  test('hamburger opens sidebar overlay on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    const hamburger = page.locator('button.lg\\:hidden');
    await hamburger.click();

    await expect(page.locator('aside')).toBeVisible();
    await expect(page.locator('aside').getByText('E2E Test Session')).toBeVisible();
  });

  test('sidebar backdrop closes sidebar on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('/');

    const hamburger = page.locator('button.lg\\:hidden');
    await hamburger.click();

    await expect(page.locator('aside')).toBeVisible();

    const backdrop = page.locator('.fixed.inset-0.z-20');
    await backdrop.click({ position: { x: 340, y: 200 } });

    await expect(page.locator('aside')).not.toBeVisible();
  });

  test('desktop viewport hides hamburger, shows sidebar', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');

    const hamburger = page.locator('button.lg\\:hidden');
    await expect(hamburger).not.toBeVisible();

    await expect(page.locator('aside')).toBeVisible();
  });
});
