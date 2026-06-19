import { test, expect } from '@playwright/test'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

test.describe('Error States', () => {
  test('start is blocked when MCP is not connected', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setMcpStatus({
      state: 'failed',
      message: 'Blender MCP could not be initialized.',
      tools: [],
    })
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')

    await expect(page.getByRole('button', { name: 'Start' })).toBeDisabled()
    await expect(page.getByText('MCP: failed')).toBeVisible()
  })

  test('run failure summary appears in activity feed', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await expect(page.getByText('activity: live')).toBeVisible()
    await expect.poll(() => mockWs.getRoute() !== null, { timeout: 10000 }).toBe(true)
    mockWs.sendSessionSnapshot(
      {
        progress: {
          workflow_type: 'multi_stage_modeling',
          status: 'failed',
          task: 'Build a chair',
          stage: 'build',
          stage_status: 'failed',
          planning_llm_prompt_preview: '',
          llm_prompt_events: [],
          active_task_id: 'task-1',
          completed_task_ids: [],
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
          stop_reason: 'Max refinement rounds reached without approval',
        },
        run_status: {
          workflow_status: 'failed',
          process_status: 'failed',
        },
      },
      TEST_SESSION_ID,
    )

    await expect(page.getByText('Max refinement rounds reached without approval', { exact: true })).toBeVisible()
  })

  test('AO validation error appends retry guidance', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await expect(page.getByText('activity: live')).toBeVisible()
    await expect.poll(() => mockWs.getRoute() !== null, { timeout: 10000 }).toBe(true)
    mockWs.sendSessionSnapshot(
      {
        progress: {
          workflow_type: 'multi_stage_modeling',
          status: 'running',
          task: 'Design a chair',
          stage: 'design',
          stage_status: 'in_progress',
          planning_llm_prompt_preview: '',
          llm_prompt_events: [
            {
              event_id: 'design:prompt:1',
              stage: 'design',
              label: 'Design',
              prompt_preview: 'Design a chair',
              response_preview: 'Here is my design',
              validation_error: 'Output format missing required fields: dimensions',
              has_images: false,
              image_count: 0,
            },
          ],
          active_task_id: '',
          completed_task_ids: [],
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
          workflow_status: 'running',
          process_status: 'running',
        },
      },
      TEST_SESSION_ID,
    )

    mockWs.sendActivityAppended([
      {
        id: 'ao-validation-error-1',
        kind: 'system',
        title: 'System',
        body: 'Agent Orchestrator response format was invalid. Agent will retry. Reason: Output format missing required fields: dimensions',
        timestamp: '09:43',
      },
    ])

    await expect(page.getByText('Agent Orchestrator response format was invalid. Agent will retry.')).toBeVisible()
    await expect(page.getByText('missing required fields: dimensions')).toBeVisible()
  })
})
