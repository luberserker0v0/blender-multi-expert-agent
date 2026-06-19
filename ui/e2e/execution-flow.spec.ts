import { test, expect, type Page } from '@playwright/test'
import { mockBridgeApi, createMockActivityWebSocket, TEST_SESSION_ID } from './helpers'

const SCREENSHOT_DIR = 'e2e/screenshots'

async function takeScreenshot(page: Page, name: string) {
  await page.screenshot({ path: `${SCREENSHOT_DIR}/${name}.png`, fullPage: false })
}

async function waitForStageChip(page: Page, stage: string, timeout = 15000) {
  const chip = page.locator('span').filter({ hasText: new RegExp(`stage:\\s*${stage}`) })
  await chip.waitFor({ state: 'visible', timeout })
}

test.describe('Multi-Expert Execution Flow', () => {
  const consoleErrors: string[] = []
  let bridge: Awaited<ReturnType<typeof mockBridgeApi>>

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
        ) {
          return
        }
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
      ) {
        return
      }
      consoleErrors.push(text)
    })

    bridge = await mockBridgeApi(page)

    await page.goto('/')
    await page.waitForLoadState('networkidle')
  })

  test.afterEach(async () => {
    expect(consoleErrors, `Console errors detected: ${JSON.stringify(consoleErrors)}`).toHaveLength(0)
  })

  test('full execution flow with stage transitions and screenshots', async ({ page }) => {
    // Pre-populate localStorage with Agent Orchestrator URL so auto-verify succeeds
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

    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.reload()
    await page.waitForLoadState('networkidle')

    await expect(page.getByText('activity: live')).toBeVisible({ timeout: 10000 })
    await expect.poll(() => mockWs.getRoute() !== null, { timeout: 10000 }).toBe(true)

    let activeSessionId = TEST_SESSION_ID

    function sendSnapshot(data: Record<string, unknown>) {
      mockWs.sendSnapshot({
        progress: data.progress as never,
        run_status: data.run_status as never,
        retry_prompt: data.retry_prompt as never,
      }, activeSessionId)
    }

    // ── 1. Create or ensure a session exists ──────────────────────────────
    const newSessionButton = page.getByRole('button', { name: /New Session/i })
    if (await newSessionButton.first().isVisible().catch(() => false)) {
      await newSessionButton.first().click()
    } else {
      const sidebarNew = page.locator('aside').getByRole('button', { name: /New Session/i })
      if (await sidebarNew.isVisible().catch(() => false)) {
        await sidebarNew.click()
      }
    }
    const taskTextarea = page.locator('textarea').first()
    await taskTextarea.waitFor({ state: 'visible', timeout: 10000 })
    activeSessionId = bridge.getState().sessions[0]?.id ?? bridge.getState().currentSessionId

    // ── 2. Fill task prompt ───────────────────────────────────────────────
    await taskTextarea.fill('Build a simple wooden chair')

    // ── 3. Wait for auto-verify to complete (AO auto-verified on session load) ──
    await expect(page.locator('text=AO: ready')).toBeVisible({ timeout: 10000 })

    await takeScreenshot(page, '01-before-start')

    // ── 4. Click Start ────────────────────────────────────────────────────
    const startButton = page.getByRole('button', { name: /^Start$/ })
    await expect(startButton).toBeEnabled({ timeout: 10000 })
    await startButton.click()

    const stages = ['design', 'spec', 'plan', 'build', 'assemble', 'validate']

    // Start with running state
    sendSnapshot({
      progress: {
        stage: stages[0],
        status: 'running',
        stage_status: 'in_progress',
        active_task_id: null,
        llm_prompt_events: [{
          event_id: `${stages[0]}:prompt:1`,
          stage: stages[0],
          prompt_preview: 'Designing a wooden chair',
          response_preview: 'Here is my design',
          validation_error: '',
        }],
        part_tasks: [],
        assembly: { rounds: [] },
        stop_reason: null,
      },
      run_status: {
        session_id: activeSessionId,
        workflow_status: 'running',
        process_status: 'running',
      },
    })

    await expect(page.locator('text=workflow: running')).toBeVisible({ timeout: 10000 })
    await waitForStageChip(page, 'design', 10000)

    // Progress through each stage
    for (let i = 0; i < stages.length; i++) {
      const stage = stages[i]

      sendSnapshot({
        progress: {
          stage,
          status: i === stages.length - 1 ? 'completed' : 'running',
          stage_status: 'in_progress',
          active_task_id: null,
          llm_prompt_events: [{
            event_id: `${stage}:prompt:1`,
            stage,
            prompt_preview: `Working on ${stage}`,
            response_preview: `${stage} completed`,
            validation_error: '',
          }],
          part_tasks: [],
          assembly: { rounds: [] },
          stop_reason: null,
        },
        run_status: {
          session_id: activeSessionId,
          workflow_status: 'running',
          process_status: 'running',
        },
      })

      await takeScreenshot(page, `03-stage-${String(i + 1).padStart(2, '0')}-${stage}`)
    }

    // ── 5. Send final completed state ─────────────────────────────────────
    sendSnapshot({
      progress: {
        stage: 'completed',
        status: 'completed',
        stage_status: 'completed',
        active_task_id: null,
        llm_prompt_events: [],
        part_tasks: [],
        assembly: {
          status: 'completed',
          current_round: 0,
          approved: true,
          all_parts_visible: true,
          initial_placement_applied: true,
          rounds: [],
        },
        final_validation: {
          status: 'completed',
          capture_path: '',
          viewpoint: 'front',
          detected_parts: ['part_1'],
          missing_critical_parts: [],
          quantitative_metrics: [],
        },
        stop_reason: null,
      },
      run_status: {
        session_id: activeSessionId,
        workflow_status: 'completed',
        process_status: 'completed',
      },
    })

    await waitForStageChip(page, 'completed', 20000)
    await expect(page.locator('text=workflow: completed')).toBeVisible({ timeout: 20000 })
    await takeScreenshot(page, '04-completed')

    // ── 6. Verify activity count remains visible after progress updates ───
    await expect(page.getByText(/\d+ messages/)).toBeVisible()
    await takeScreenshot(page, '05-activity-count')

    await expect(page.locator('text=This run failed')).not.toBeVisible()
  })
})
