import { test, expect } from '@playwright/test'
import type { ActivityItem } from '../src/types'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

function llmItem(overrides?: Partial<ActivityItem>): ActivityItem {
  return {
    id: `activity-${Math.random()}`,
    kind: 'llm',
    title: 'designer',
    body: 'Prompt > Design\n\nDesign a wooden chair',
    timestamp: '09:41',
    collapsible: true,
    responseBody: 'Full AO response for inspection',
    pairLabel: 'design',
    llmDirection: 'prompt',
    ...overrides,
  }
}

test.describe('Conversation Surface', () => {
  test('renders empty state with skeleton placeholders', async ({ page }, testInfo) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Conversation Surface' })).toBeVisible()
    await expect(page.getByText('0 messages')).toBeVisible()

    const screenshotPath = testInfo.outputPath('conversation-empty.png')
    await page.screenshot({ path: screenshotPath })
    await testInfo.attach('conversation-empty', { path: screenshotPath })
  })

  test('receives meeting events and appends them in order', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await expect(page.getByText('activity: live')).toBeVisible()

    mockWs.sendMeetingEvent({
      event_id: 'design:phase_start:100',
      phase: 'design',
      kind: 'phase_start',
      message: 'Design meeting started',
    })
    mockWs.sendMeetingEvent({
      event_id: 'design:expert_spoke:101',
      phase: 'design',
      kind: 'expert_spoke',
      message: 'The designer proposes a balanced chair silhouette.',
      speaker: 'designer',
      turn: 1,
      content_preview: 'Balanced chair silhouette',
    })
    mockWs.sendMeetingEvent({
      event_id: 'design:build_step:102',
      phase: 'design',
      kind: 'build_step',
      message: 'Building chair_leg base mesh',
    })

    await expect(page.getByText('Design Phase')).toBeVisible()
    await expect(page.getByText('Balanced chair silhouette')).toBeVisible()
    await expect(page.getByText('Building chair_leg base mesh')).toBeVisible()
    await expect(page.getByText('3 messages')).toBeVisible()
  })

  test('activity_appended updates message count and allows AO expansion', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendActivityAppended([
      llmItem(),
      {
        id: 'feedback-1',
        kind: 'feedback',
        title: 'Feedback',
        body: 'Leg geometry needs a thicker base.',
        timestamp: '09:42',
      },
    ])

    await expect(page.getByText('2 messages')).toBeVisible()
    await expect(page.getByText('Leg geometry needs a thicker base.')).toBeVisible()
    await page.getByText('Prompt > Design').click()
    await expect(page.getByText('Full AO response for inspection')).toBeVisible()
  })

  test('snapshot_required refreshes activity and sync state from session snapshot', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setActivity(TEST_SESSION_ID, [
      {
        id: 'status-1',
        kind: 'status',
        title: 'Status',
        body: 'design / in_progress',
        timestamp: '09:41',
      },
      {
        id: 'system-1',
        kind: 'system',
        title: 'System',
        body: 'Planning completed: 2 tasks - Chair Leg, Chair Seat.',
        timestamp: '09:42',
      },
    ])
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)

    await expect(page.getByText('design / in_progress')).toBeVisible()
    await expect(page.getByText('Planning completed: 2 tasks - Chair Leg, Chair Seat.')).toBeVisible()
    await expect(page.getByText('2 messages')).toBeVisible()
  })

  test('replaying the same snapshot and mixed websocket events converges to one visible timeline state', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const persistedItem: ActivityItem = {
      id: 'persisted-1',
      kind: 'system',
      title: 'System',
      body: 'Planning completed: 2 tasks - Chair Leg, Chair Seat.',
      timestamp: '09:42',
    }
    bridge.setActivity(TEST_SESSION_ID, [persistedItem])
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)

    await expect(page.getByText('Planning completed: 2 tasks - Chair Leg, Chair Seat.')).toBeVisible()
    await expect(page.getByText('1 messages')).toBeVisible()

    mockWs.sendMeetingEvent({
      event_id: 'design:expert_spoke:201',
      phase: 'design',
      kind: 'expert_spoke',
      message: 'The designer confirms the chair proportions.',
      speaker: 'designer',
      content_preview: 'Chair proportions confirmed',
    })
    await expect(page.getByText('2 messages')).toBeVisible()
    await expect(page.getByText('Chair proportions confirmed')).toBeVisible()

    mockWs.sendSessionSnapshot({ activity: [persistedItem] }, TEST_SESSION_ID)
    await expect(page.getByText('1 messages')).toBeVisible()
    await expect(page.getByText('Planning completed: 2 tasks - Chair Leg, Chair Seat.')).toHaveCount(1)
    await expect(page.getByText('Chair proportions confirmed')).toHaveCount(0)
  })

  test('retry cards render for waiting and auto-retrying states', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setRetryPrompt(TEST_SESSION_ID, {
      show: true,
      failure_reason: 'Part build failed: mesh has non-manifold edges',
      attempt_index: 1,
      next_attempt_index: 2,
      decision_state: 'awaiting',
      remaining_retries: 2,
    })
    bridge.setRunStatus(TEST_SESSION_ID, {
      workflow_status: 'failed',
      process_status: 'failed',
      attempt_index: 1,
    })
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)

    await expect(page.getByText('Retry 1')).toBeVisible()
    await expect(page.getByText('Retry 3')).toBeVisible()
    await expect(page.getByText('Stop retrying')).toBeVisible()
    await expect(page.getByText('non-manifold edges')).toBeVisible()

    bridge.setRetryPrompt(TEST_SESSION_ID, {
      show: false,
      auto_retrying: true,
      remaining_retries: 1,
      attempt_index: 2,
      next_attempt_index: 3,
      decision_state: 'auto_retrying',
    })
    bridge.setRunStatus(TEST_SESSION_ID, {
      workflow_status: 'running',
      process_status: 'running',
      attempt_index: 2,
    })
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)

    await expect(page.getByText('Auto retry is running. The agent is preparing attempt 3.')).toBeVisible()
    await expect(page.getByText('Remaining retry budget: 1')).toBeVisible()
  })
})
