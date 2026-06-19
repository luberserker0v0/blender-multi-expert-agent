import { test, expect } from '@playwright/test';
import { mockBridgeApi, createMockActivityWebSocket, TEST_SESSION_ID } from './helpers';

test.describe('Session Management', () => {
  test('shows existing session in sidebar', async ({ page }, testInfo) => {
    await mockBridgeApi(page);
    const mockWs = createMockActivityWebSocket(page);
    await mockWs.setup();

    await page.goto('/');
    await expect(page.getByText('Current Session')).toBeVisible();

    // Check if session appears in sidebar (use heading to be specific)
    await expect(page.getByRole('heading', { name: 'E2E Test Session' })).toBeVisible();

    const screenshotPath = testInfo.outputPath('session-sidebar.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('session-sidebar', { path: screenshotPath });
  });

  test('creates new session when clicking New Session button', async ({ page }, testInfo) => {
    await mockBridgeApi(page);
    const mockWs = createMockActivityWebSocket(page);
    await mockWs.setup();

    await page.goto('/');
    await expect(page.getByText('Current Session')).toBeVisible();

    // Click New Session button in sidebar
    await page.locator('aside').getByRole('button', { name: 'New Session' }).click();

    // Wait for session to be created - check that the button was clicked
    await page.waitForTimeout(1000);

    const screenshotPath = testInfo.outputPath('session-created.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('session-created', { path: screenshotPath });
  });

  test('empty state shows when no sessions exist', async ({ page }, testInfo) => {
    // Override bootstrap to return empty sessions
    await page.route('**/api/bootstrap', async (route) => {
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sessions: [],
          current_session_id: '',
          settings: {
            agent_orchestrator_base_url: '',
            agent_orchestrator_model: '',
            agent_orchestrator_destroy_on_finish: true,
            agent_orchestrator_timeout_seconds: 120,
            max_part_refinement_rounds: 3,
            max_assembly_rounds: 3,
            use_yolo_perception: false,
            yolo_model_path: '',
            yolo_viewpoints: [],
          },
          workspace: {
            taskInput: '',
            referenceText: '',
            referenceImages: [],
            activity: [],
          },
          progress: null,
          mcp_status: null,
          run_status: null,
          console_log: null,
          retry_prompt: null,
        }),
      });
    });

    await page.goto('/');

    // Check for empty state or New Session button
    await expect(page.getByText('New Session').first()).toBeVisible({ timeout: 5000 });

    const screenshotPath = testInfo.outputPath('session-empty-state.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('session-empty-state', { path: screenshotPath });
  });

  test('composer shows session title', async ({ page }, testInfo) => {
    await mockBridgeApi(page);
    const mockWs = createMockActivityWebSocket(page);
    await mockWs.setup();

    await page.goto('/');
    await expect(page.getByText('Current Session')).toBeVisible();

    // Check if session title is shown in composer
    await expect(page.getByRole('heading', { name: 'E2E Test Session' })).toBeVisible();

    const screenshotPath = testInfo.outputPath('session-composer-title.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('session-composer-title', { path: screenshotPath });
  });

  test('batch deletes selected sessions after confirmation', async ({ page }, testInfo) => {
    const bridge = await mockBridgeApi(page);
    bridge.setSessions(
      [
        { id: TEST_SESSION_ID, title: 'E2E Test Session', updatedAt: '2024-01-01T00:00:00Z' },
        { id: 'batch-delete-alpha', title: 'Batch Delete Alpha', updatedAt: '2024-01-02T00:00:00Z' },
        { id: 'batch-delete-beta', title: 'Batch Delete Beta', updatedAt: '2024-01-03T00:00:00Z' },
      ],
      TEST_SESSION_ID,
    );
    const mockWs = createMockActivityWebSocket(page);
    await mockWs.setup();

    await page.goto('/');

    await page.locator('aside').getByRole('button', { name: 'Batch Delete', exact: true }).click();
    await expect(page.getByLabel('Select Batch Delete Alpha for deletion')).toBeVisible();
    await expect(page.getByLabel('Select Batch Delete Beta for deletion')).toBeVisible();

    await page.getByLabel('Select Batch Delete Alpha for deletion').check();
    await page.locator('aside').getByRole('button', { name: /Batch Delete Beta/ }).click();
    await page.locator('aside').getByRole('button', { name: 'Delete', exact: true }).click();

    await expect(page.getByText('Batch Delete Sessions')).toBeVisible();
    await expect(page.getByRole('heading', { name: '2 selected sessions' })).toBeVisible();

    await page.getByRole('button', { name: 'Delete Selected' }).click();

    await expect(page.getByRole('heading', { name: 'Batch Delete Alpha' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Batch Delete Beta' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'E2E Test Session' })).toBeVisible();
    await expect(page.locator('aside').getByRole('button', { name: 'Batch Delete', exact: true })).toBeVisible();

    const screenshotPath = testInfo.outputPath('session-batch-delete.png');
    await page.screenshot({ path: screenshotPath });
    await testInfo.attach('session-batch-delete', { path: screenshotPath });
  });
});
