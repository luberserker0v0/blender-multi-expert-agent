import { expect, test } from '@playwright/test'
import {
  buildExpectedActivityTimeline,
  buildExpectedActivityFromEventTrace,
  createFreshSessionFromUi,
  expectActivityEventTraceInRenderedOrder,
  expectActivityTimelineToMatch,
  expectNoDuplicateRenderedEventDrivenItems,
  fetchBackendActivityEventTrace,
  fetchBackendActivityTruth,
  readCurrentSessionId,
  waitForActivityTimelineLength,
  waitForWorkflowState,
} from './live-bridge-helpers'

test.describe('Live Bridge Activity Event Order', () => {
  test('keeps websocket meeting events and resync boundaries aligned with the rendered activity timeline', async ({
    page,
  }) => {
    test.setTimeout(120000)

    await page.addInitScript(() => {
      localStorage.clear()
    })

    await page.goto('/')
    await expect(page.getByText(/Current Session|Start with a new session/)).toBeVisible()

    await createFreshSessionFromUi(page)

    const taskTextarea = page.getByPlaceholder(
      'Example: Build a wooden chair with a straight backrest and square seat.',
    )
    await taskTextarea.fill('Audit websocket activity event ordering for a wooden chair')

    await expect(page.getByText('MCP: connected')).toBeVisible({ timeout: 10000 })
    await expect(page.getByText('AO: ready')).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('button', { name: 'Start' })).toBeEnabled()
    await page.getByRole('button', { name: 'Start' }).click()

    const sessionId = await readCurrentSessionId(page)
    expect(sessionId).toBeTruthy()

    await waitForWorkflowState(page, 'running', 20000)
    await expect
      .poll(async () => buildExpectedActivityFromEventTrace(await fetchBackendActivityEventTrace(page, sessionId)).length, {
        timeout: 20000,
      })
      .toBeGreaterThanOrEqual(1)

    await waitForActivityTimelineLength(page, 1, 20000)

    const runningTrace = await fetchBackendActivityEventTrace(page, sessionId)
    await expectActivityEventTraceInRenderedOrder(page, runningTrace)

    await expect
      .poll(
        async () =>
          (await fetchBackendActivityEventTrace(page, sessionId)).events.filter(
            (event) => event.type === 'snapshot_required',
          ).length,
        { timeout: 20000 },
      )
      .toBeGreaterThanOrEqual(1)

    const postResyncTrace = await fetchBackendActivityEventTrace(page, sessionId)
    await expectActivityEventTraceInRenderedOrder(page, postResyncTrace)
    await expectNoDuplicateRenderedEventDrivenItems(page, postResyncTrace)

    await waitForWorkflowState(page, 'completed', 40000)

    const finalTrace = await fetchBackendActivityEventTrace(page, sessionId)
    await expectActivityEventTraceInRenderedOrder(page, finalTrace)
    await expectNoDuplicateRenderedEventDrivenItems(page, finalTrace)

    const finalTruth = await fetchBackendActivityTruth(page, sessionId)
    await expectActivityTimelineToMatch(page, buildExpectedActivityTimeline(finalTruth.snapshot))
  })
})
