import { test, expect } from '@playwright/test'
import { createMockActivityWebSocket, mockBridgeApi, TEST_SESSION_ID } from './helpers'

test.describe('Advanced UI Flows', () => {
  test('snapshot updates produce AO turn, feedback, and retry activity states', async ({ page }) => {
    const bridge = await mockBridgeApi(page)
    const mockWs = createMockActivityWebSocket(page, bridge)
    await mockWs.setup()

    await page.goto('/')
    await expect(page.getByText('activity: live')).toBeVisible()

    mockWs.sendSessionSnapshot(
      {
        progress: {
          workflow_type: 'multi_stage_modeling',
          status: 'running',
          task: 'Build a wooden chair',
          stage: 'design',
          stage_status: 'in_progress',
          planning_llm_prompt_preview: '',
          llm_prompt_events: [
            {
              event_id: 'design:prompt:1',
              stage: 'design',
              label: 'Design',
              prompt_preview: 'Design a wooden chair',
              response_preview: 'Here is my design for a wooden chair with 4 legs',
              validation_error: '',
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

    mockWs.sendMeetingEvent({
      event_id: 'design:proposal:1',
      phase: 'design',
      kind: 'proposal',
      speaker: 'designer',
      summary: 'Here is my design for a wooden chair with 4 legs',
      full_content: 'Here is my design for a wooden chair with 4 legs',
      message: 'Here is my design for a wooden chair with 4 legs',
    })

    await expect(page.getByText('Here is my design for a wooden chair with 4 legs')).toBeVisible()

    mockWs.sendSessionSnapshot(
      {
        progress: {
          workflow_type: 'multi_stage_modeling',
          status: 'running',
          task: 'Build a wooden chair',
          stage: 'build',
          stage_status: 'in_progress',
          planning_llm_prompt_preview: '',
          llm_prompt_events: [],
          active_task_id: 'task-1',
          completed_task_ids: [],
          part_tasks: [
            {
              task_id: 'task-1',
              title: 'Build Chair Leg',
              object_name: 'chair_leg',
              status: 'in_progress',
              current_round: 1,
              approved: false,
              hidden_after_approval: false,
              rounds: [
                {
                  round_index: 1,
                  capture_path: 'captures/chair-leg.png',
                  viewpoint: 'front',
                  approved: false,
                  llm_prompt_preview: '',
                  feedback_summary: 'The leg geometry needs to be thicker at the base',
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
        },
      },
      TEST_SESSION_ID,
    )

    mockWs.sendMeetingEvent({
      event_id: 'build:validation_result:1',
      phase: 'build',
      kind: 'validation_result',
      summary: 'The leg geometry needs to be thicker at the base',
      full_content: 'The leg geometry needs to be thicker at the base',
      message: 'The leg geometry needs to be thicker at the base',
    })

    await expect(page.getByText('The leg geometry needs to be thicker at the base')).toBeVisible()

    mockWs.sendSessionSnapshot(
      {
        progress: {
          workflow_type: 'multi_stage_modeling',
          status: 'failed',
          task: 'Build a wooden chair',
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
          stop_reason: 'build_failed',
        },
        run_status: {
          workflow_status: 'failed',
          process_status: 'failed',
          attempt_index: 1,
        },
        retry_prompt: {
          show: true,
          session_id: TEST_SESSION_ID,
          failure_reason: 'Part build failed: mesh has non-manifold edges',
          attempt_index: 1,
          next_attempt_index: 2,
          decision_state: 'awaiting',
          auto_retrying: false,
          remaining_retries: 2,
        },
      },
      TEST_SESSION_ID,
    )

    await expect(page.getByText('Retry 1')).toBeVisible()
    await expect(page.getByText('non-manifold edges')).toBeVisible()
  })
})
