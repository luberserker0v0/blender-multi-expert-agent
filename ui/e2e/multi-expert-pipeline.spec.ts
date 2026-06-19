import { test, expect, type Page } from '@playwright/test'
import { mockBridgeApi, createMockActivityWebSocket, TEST_SESSION_ID } from './helpers'

function sendSnapshot(
  mockWs: ReturnType<typeof createMockActivityWebSocket>,
  stage: string,
  status: string,
  workflow: string,
) {
  mockWs.sendSnapshot({
    progress: {
      stage,
      status,
      stage_status: status === 'completed' ? 'completed' : 'in_progress',
      active_task_id: '',
      llm_prompt_events: [],
      part_tasks: [],
      assembly: {
        status: 'pending',
        current_round: 0,
        approved: false,
        all_parts_visible: false,
        initial_placement_applied: false,
        rounds: [],
      },
      final_validation: {
        status: 'pending',
        capture_path: '',
        viewpoint: 'front',
        detected_parts: [],
        missing_critical_parts: [],
        quantitative_metrics: [],
      },
      stop_reason: '',
    },
    run_status: {
      session_id: TEST_SESSION_ID,
      workflow_status: workflow as 'running' | 'completed',
      process_status: workflow === 'completed' ? 'completed' : 'running',
    },
  })
}

async function waitForWsRoute(mockWs: ReturnType<typeof createMockActivityWebSocket>, page: Page) {
  await expect(page.getByText('activity: live')).toBeVisible({ timeout: 10000 })
  await expect.poll(() => mockWs.getRoute() !== null, { timeout: 10000 }).toBe(true)
}

test.describe('Multi-Expert Pipeline Conversation', () => {
  const consoleErrors: string[] = []

  test.beforeEach(async ({ page }) => {
    consoleErrors.length = 0
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text()
        if (
          text.includes('WebSocket connection') ||
          text.includes('ERR_CONNECTION_REFUSED') ||
          text.includes('[vite] failed to connect to websocket') ||
          text.includes("Cannot read properties of undefined (reading 'send')")
        ) return
        consoleErrors.push(text)
      }
    })
    page.on('pageerror', (err) => {
      const text = err.message
      if (
        text.includes('WebSocket connection') ||
        text.includes('ERR_CONNECTION_REFUSED') ||
        text.includes('[vite] failed to connect to websocket') ||
        text.includes("Cannot read properties of undefined (reading 'send')")
      ) return
      consoleErrors.push(text)
    })
  })

  test.afterEach(async () => {
    expect(consoleErrors, `Console errors: ${JSON.stringify(consoleErrors)}`).toHaveLength(0)
  })

  test('fills prompt, starts run, and renders the multi-phase conversation', async ({ page }) => {
    await page.addInitScript(() => {
      localStorage.setItem('ai3d-react-ui-settings', JSON.stringify({
        agentOrchestratorUrl: 'http://127.0.0.1:4111',
        agentOrchestratorModel: '',
        keepAgentOrchestratorConversation: false,
        agentOrchestratorTimeoutSeconds: 120,
        maxPartRefinementRounds: 3,
        maxAssemblyRounds: 3,
        useYoloValidation: false,
        yoloModelPath: '',
        yoloViewpoints: '',
      }))
    })

    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await page.waitForLoadState('networkidle')

    await expect(page.getByRole('heading', { name: 'Conversation Surface' })).toBeVisible()
    await waitForWsRoute(mockWs, page)

    const textarea = page.locator('textarea').first()
    await textarea.fill('Build a wooden chair with 4 legs')
    await expect(page.getByText('AO: ready')).toBeVisible()

    const startBtn = page.getByRole('button', { name: /^Start$/ })
    await expect(startBtn).toBeEnabled()
    await startBtn.click()

    sendSnapshot(mockWs, 'design', 'running', 'running')
    await expect(page.getByText('workflow: running')).toBeVisible()
    await expect(page.locator('span').filter({ hasText: /stage:\s*design/ }).first()).toBeVisible()

    mockWs.sendMeetingEvent({
      event_id: 'design:phase_start:1',
      phase: 'design',
      kind: 'phase_start',
      message: 'Design meeting started',
    })
    mockWs.sendMeetingEvent({
      event_id: 'design:expert_spoke:1',
      phase: 'design',
      kind: 'expert_spoke',
      speaker: 'designer',
      turn: 1,
      content_preview: 'I will design a wooden chair with 4 legs',
      message: 'I will design a wooden chair with 4 legs, each leg 45cm tall.',
    })
    mockWs.sendMeetingEvent({
      event_id: 'design:expert_spoke:2',
      phase: 'design',
      kind: 'expert_spoke',
      speaker: 'reviewer',
      turn: 2,
      content_preview: 'Design looks good, legs need thicker base',
      message: 'The design looks good, but the legs need to be thicker at the base.',
    })
    mockWs.sendMeetingEvent({
      event_id: 'design:artifact_written:1',
      phase: 'design',
      kind: 'validation_result',
      message: 'design.md artifact saved: seat and leg decisions recorded',
    })

    await expect(page.getByText('Design Phase')).toBeVisible()
    await expect(page.getByText('designer')).toBeVisible()
    await expect(page.getByText('reviewer')).toBeVisible()
    await expect(page.getByText('design.md artifact saved: seat and leg decisions recorded')).toBeVisible()

    sendSnapshot(mockWs, 'spec', 'running', 'running')
    await expect(page.locator('span').filter({ hasText: /stage:\s*spec/ }).first()).toBeVisible()
    mockWs.sendMeetingEvent({
      event_id: 'spec:phase_start:1',
      phase: 'spec',
      kind: 'phase_start',
      message: 'Spec meeting started',
    })
    mockWs.sendMeetingEvent({
      event_id: 'spec:expert_spoke:1',
      phase: 'spec',
      kind: 'expert_spoke',
      speaker: 'spec_analyst',
      turn: 1,
      content_preview: 'Chair dimensions: 90cm height, 45cm seat width',
      message: 'Chair dimensions: 90cm height, 45cm seat width',
    })

    await expect(page.getByText('Spec Phase')).toBeVisible()
    await expect(page.getByText('Chair dimensions: 90cm height, 45cm seat width', { exact: true })).toBeVisible()

    sendSnapshot(mockWs, 'build', 'running', 'running')
    await expect(page.locator('span').filter({ hasText: /stage:\s*build/ }).first()).toBeVisible()
    mockWs.sendMeetingEvent({
      event_id: 'build:build_step:1',
      phase: 'build',
      kind: 'build_step',
      message: 'Building chair leg part_1...',
    })
    await expect(page.getByText('Building chair leg part_1...')).toBeVisible()

    sendSnapshot(mockWs, 'assemble', 'running', 'running')
    await expect(page.locator('span').filter({ hasText: /stage:\s*assemble/ }).first()).toBeVisible()
    mockWs.sendMeetingEvent({
      event_id: 'assemble:assemble_step:1',
      phase: 'assemble',
      kind: 'assemble_step',
      message: 'Assembling all parts into final model',
    })
    await expect(page.getByText('Assembling all parts into final model')).toBeVisible()

    sendSnapshot(mockWs, 'completed', 'completed', 'completed')

    await expect(page.getByText('workflow: completed')).toBeVisible()
    await expect(page.getByText('This run failed')).not.toBeVisible()
  })
})
