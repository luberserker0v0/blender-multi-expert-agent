import { expect, test } from '@playwright/test'
import {
  buildExpectedActivityTimeline,
  closeTopPanel,
  createFreshSessionFromUi,
  expectActivityTimelineToMatch,
  expectInspectorPanelToMatch,
  expectRetryCardToMatch,
  expectRuntimePanelToMatch,
  fetchBackendActivityTruth,
  fetchBackendInspectorTruth,
  fetchBackendRetryTruth,
  fetchBackendRuntimeTruth,
  openInspector,
  openRuntimeLog,
  readCurrentSessionId,
  waitForWorkflowState,
} from './live-bridge-helpers'

test.describe('Live Bridge Retry Smoke', () => {
  test('fails once, shows retry prompt, and succeeds after retry with truth-aligned UI', async ({ page }) => {
    test.setTimeout(120000)
    await page.addInitScript(() => {
      localStorage.clear()
    })

    await page.goto('/')
    await createFreshSessionFromUi(page)

    await page
      .getByPlaceholder('Example: Build a wooden chair with a straight backrest and square seat.')
      .fill('[retry-smoke] Build a simple wooden chair')

    await expect(page.getByText('MCP: connected')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('AO: ready')).toBeVisible({ timeout: 10000 })
    await page.getByRole('button', { name: 'Start' }).click()

    const sessionId = await readCurrentSessionId(page)
    expect(sessionId).toBeTruthy()

    await expect
      .poll(async () => (await fetchBackendRetryTruth(page, sessionId)).run_status.workflow_status, { timeout: 30000 })
      .toBe('failed')
    await waitForWorkflowState(page, 'failed', 30000)

    const failureRetryTruth = await fetchBackendRetryTruth(page, sessionId)
    expect(failureRetryTruth.run_status.workflow_status).toBe('failed')
    expect(String(failureRetryTruth.pending_interaction.status ?? '')).toBe('pending')
    await expectRetryCardToMatch(page, failureRetryTruth)

    const failureActivityTruth = await fetchBackendActivityTruth(page, sessionId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(failureActivityTruth.snapshot))

    await openRuntimeLog(page)
    const failureRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionId)
    await expectRuntimePanelToMatch(page, failureRuntimeTruth)
    await expect(page.getByText('Mock retry smoke failure triggered')).toBeVisible({ timeout: 20000 })
    await expect(page.getByTestId('runtime-console')).toContainText(
      'Validation failed for seat; waiting for retry decision',
      { timeout: 20000 },
    )
    await closeTopPanel(page)

    await openInspector(page)
    const failureInspectorTruth = await fetchBackendInspectorTruth(page, sessionId)
    await expectInspectorPanelToMatch(page, failureInspectorTruth)
    await closeTopPanel(page)

    await page.getByTestId('retry-card-action-retry-1').click()
    await waitForWorkflowState(page, 'running', 20000)

    const retryRunningTruth = await fetchBackendRetryTruth(page, sessionId)
    expect(retryRunningTruth.run_status.attempt_index).toBeGreaterThanOrEqual(2)
    expect(retryRunningTruth.run_status.workflow_status).toBe('running')
    expect(retryRunningTruth.retry_prompt.decision_state).toBe('retrying')
    await expectRetryCardToMatch(page, retryRunningTruth)
    await expect(page.getByText('sync: live').first()).toBeVisible()
    await expect(page.getByText(/\d+ messages/)).toBeVisible()

    await openRuntimeLog(page)
    const retryRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionId)
    await expectRuntimePanelToMatch(page, retryRuntimeTruth)
    await expect(page.getByText('=== RETRY ATTEMPT START ===')).toBeVisible({ timeout: 20000 })
    await closeTopPanel(page)

    await openInspector(page)
    const retryInspectorTruth = await fetchBackendInspectorTruth(page, sessionId)
    await expectInspectorPanelToMatch(page, retryInspectorTruth)
    await closeTopPanel(page)

    await waitForWorkflowState(page, 'completed', 50000)

    const completedRetryTruth = await fetchBackendRetryTruth(page, sessionId)
    expect(completedRetryTruth.run_status.workflow_status).toBe('completed')
    expect(completedRetryTruth.retry_prompt.show).toBe(false)

    const completedActivityTruth = await fetchBackendActivityTruth(page, sessionId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(completedActivityTruth.snapshot))

    await openRuntimeLog(page)
    const completedRuntimeTruth = await fetchBackendRuntimeTruth(page, sessionId)
    await expectRuntimePanelToMatch(page, completedRuntimeTruth)
    await closeTopPanel(page)

    await openInspector(page)
    const completedInspectorTruth = await fetchBackendInspectorTruth(page, sessionId)
    await expectInspectorPanelToMatch(page, completedInspectorTruth)
    await closeTopPanel(page)
  })

  test('can stop retrying after failure without auto-restarting', async ({ page }) => {
    test.setTimeout(90000)
    await page.addInitScript(() => {
      localStorage.clear()
    })

    await page.goto('/')
    await createFreshSessionFromUi(page)

    await page
      .getByPlaceholder('Example: Build a wooden chair with a straight backrest and square seat.')
      .fill('[retry-smoke] Build a simple wooden chair')

    await expect(page.getByText('MCP: connected')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('AO: ready')).toBeVisible({ timeout: 10000 })
    await page.getByRole('button', { name: 'Start' }).click()

    const sessionId = await readCurrentSessionId(page)
    expect(sessionId).toBeTruthy()

    await expect
      .poll(async () => (await fetchBackendRetryTruth(page, sessionId)).run_status.workflow_status, { timeout: 30000 })
      .toBe('failed')
    await waitForWorkflowState(page, 'failed', 30000)

    const failureTruth = await fetchBackendRetryTruth(page, sessionId)
    await expectRetryCardToMatch(page, failureTruth)

    await page.getByTestId('retry-card-action-stop').click()
    await expect(page.getByTestId('retry-card')).toBeHidden({ timeout: 20000 })
    await page.waitForTimeout(1500)

    const stoppedTruth = await fetchBackendRetryTruth(page, sessionId)
    expect(stoppedTruth.retry_prompt.show).toBe(false)
    expect(String(stoppedTruth.pending_interaction.resolved_action ?? '')).toBe('stop')
    expect(stoppedTruth.retry_prompt.decision_state).toBe('stopped')
    expect(stoppedTruth.run_status.workflow_status).toBe('failed')
    await expectRetryCardToMatch(page, stoppedTruth)
    await expect(page.getByText('workflow: failed')).toBeVisible()

    const stoppedActivityTruth = await fetchBackendActivityTruth(page, sessionId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(stoppedActivityTruth.snapshot))
  })
})
