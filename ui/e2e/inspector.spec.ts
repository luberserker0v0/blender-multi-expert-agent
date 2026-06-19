import { test, expect } from '@playwright/test'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

test.describe('Inspector Panel', () => {
  test('shows skeleton state while progress is idle', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await page.getByRole('button', { name: 'Inspector' }).click()

    await expect(page.getByRole('heading', { name: 'Progress Inspector' })).toBeVisible()
    await expect(page.getByText('Latest Capture')).not.toBeVisible()
  })

  test('renders progress summary, captures, and inspector blocks from snapshot', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setProgress(TEST_SESSION_ID, {
      workflow_type: 'multi_stage_modeling',
      status: 'running',
      task: 'Build a chair',
      stage: 'build',
      stage_status: 'in_progress',
      active_task_id: 'chair-leg',
      completed_task_ids: ['chair-seat'],
      llm_prompt_events: [],
      part_tasks: [
        {
          task_id: 'chair-leg',
          title: 'Chair Leg',
          object_name: 'chair_leg',
          status: 'in_progress',
          current_round: 2,
          approved: false,
          hidden_after_approval: false,
          rounds: [
            {
              round_index: 2,
              capture_path: 'captures/chair-leg-round-2.png',
              viewpoint: 'front',
              approved: false,
              llm_prompt_preview: '',
              feedback_summary: 'Leg needs a thicker base',
              context: {
                current_mode: 'OBJECT',
                active_object_name: 'chair_leg',
                active_element_mode: 'NONE',
              },
              requested_action: null,
            },
          ],
        },
      ],
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
        capture_path: 'captures/final.png',
        viewpoint: 'front',
        detected_parts: ['chair-seat'],
        missing_critical_parts: [],
        quantitative_metrics: [],
      },
      stop_reason: '',
      planning_llm_prompt_preview: '',
    })

    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)
    await page.getByRole('button', { name: 'Inspector' }).click()

    await expect(page.getByText('build / in_progress', { exact: true })).toBeVisible()
    await expect(page.getByText('captures/chair-leg-round-2.png')).toBeVisible()
    await expect(page.getByText('captures/final.png')).toBeVisible()
    await expect(page.getByText('Chair Leg')).toBeVisible()
    await expect(page.getByText('Task Summary')).toBeVisible()
    await expect(page.getByText('chair_leg')).toBeVisible()
    await expect(page.getByText('current_round')).toBeVisible()
  })

  test('does not fall back to the first task when active_task_id is invalid', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setProgress(TEST_SESSION_ID, {
      workflow_type: 'multi_stage_modeling',
      status: 'running',
      task: 'Build a chair',
      stage: 'build',
      stage_status: 'in_progress',
      active_task_id: 'missing-task',
      completed_task_ids: [],
      llm_prompt_events: [],
      part_tasks: [
        {
          task_id: 'chair-leg',
          title: 'Chair Leg',
          object_name: 'chair_leg',
          status: 'in_progress',
          current_round: 2,
          approved: false,
          hidden_after_approval: false,
          rounds: [
            {
              round_index: 2,
              capture_path: 'captures/chair-leg-round-2.png',
              viewpoint: 'front',
              approved: false,
              llm_prompt_preview: '',
              feedback_summary: 'Leg needs a thicker base',
              context: {
                current_mode: 'OBJECT',
                active_object_name: 'chair_leg',
                active_element_mode: 'NONE',
              },
              requested_action: null,
            },
          ],
        },
      ],
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
      planning_llm_prompt_preview: '',
    })

    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)
    await page.getByRole('button', { name: 'Inspector' }).click()

    await expect(page.getByTestId('inspector-selected-task-title')).toHaveText('No active task selected')
    await expect(page.getByText('Task Summary')).not.toBeVisible()
    await expect(page.getByText('No inspector details are available yet.')).toBeVisible()
    await expect(page.getByTestId('inspector-capture-latest-path')).toHaveText('No capture selected')
  })

  test('prefers assembly round details during assembly stage', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    bridge.setProgress(TEST_SESSION_ID, {
      workflow_type: 'multi_stage_modeling',
      status: 'running',
      task: 'Build a chair',
      stage: 'assembly',
      stage_status: 'in_progress',
      active_task_id: 'chair-leg',
      completed_task_ids: ['chair-seat'],
      llm_prompt_events: [],
      part_tasks: [
        {
          task_id: 'chair-leg',
          title: 'Chair Leg',
          object_name: 'chair_leg',
          status: 'in_progress',
          current_round: 2,
          approved: false,
          hidden_after_approval: false,
          rounds: [
            {
              round_index: 2,
              capture_path: 'captures/chair-leg-round-2.png',
              viewpoint: 'front',
              approved: false,
              llm_prompt_preview: '',
              feedback_summary: 'Leg needs a thicker base',
              context: {
                current_mode: 'OBJECT',
                active_object_name: 'chair_leg',
                active_element_mode: 'NONE',
              },
              requested_action: null,
            },
          ],
        },
      ],
      assembly: {
        status: 'in_progress',
        current_round: 1,
        approved: false,
        all_parts_visible: true,
        initial_placement_applied: true,
        rounds: [
          {
            round_index: 1,
            task_id: 'chair-leg',
            task_title: 'Chair Leg',
            assembly_step_index: 1,
            capture_path: 'captures/assembly-round-1.png',
            viewpoint: 'front',
            approved: false,
            llm_prompt_preview: '',
            feedback_summary: 'Assembly alignment needs adjustment',
            context: {
              current_mode: 'OBJECT',
              active_object_name: 'chair_leg',
              active_element_mode: 'NONE',
            },
            requested_actions: [
              {
                action_type: 'move_object',
                execution_status: 'pending',
                reason: 'Leg alignment is off',
                parameters: {
                  axis: 'x',
                  delta: '0.02',
                },
              },
            ],
          },
        ],
      },
      final_validation: {
        status: 'pending',
        capture_path: 'captures/final.png',
        viewpoint: 'front',
        detected_parts: ['chair-seat'],
        missing_critical_parts: [],
        quantitative_metrics: [],
      },
      stop_reason: '',
      planning_llm_prompt_preview: '',
    })

    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    mockWs.sendSnapshotRequired(TEST_SESSION_ID)
    await page.getByRole('button', { name: 'Inspector' }).click()

    await expect(page.getByTestId('inspector-selected-task-title')).toHaveText('Assembly Round 1')
    await expect(page.getByTestId('inspector-capture-latest-path')).toHaveText('captures/assembly-round-1.png')
    await expect(page.getByTestId('inspector-block-title').filter({ hasText: 'Assembly Round' })).toBeVisible()
    await expect(page.getByText('task_title')).toBeVisible()
    await expect(page.getByText('assembly_step_index')).toBeVisible()
    await expect(page.getByText('Requested Action 1')).toBeVisible()
  })
})
