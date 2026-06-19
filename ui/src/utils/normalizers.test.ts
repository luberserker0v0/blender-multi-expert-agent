import { describe, it, expect } from 'vitest'
import { normalizeProgress, createEmptyProgress } from './normalizers'
import { mockPlanningSnapshot, mockPartRefinementSnapshot } from '../test/fixtures'
import type { MultiStageProgressSnapshot } from '../types'

const defaultProgress = createEmptyProgress()

function stripLlmFields(snapshot: MultiStageProgressSnapshot): MultiStageProgressSnapshot {
  // Snapshot comparison ignores optional LLM fields we don't set in tests
  const rest = { ...snapshot }
  delete rest.llm_prompt_events
  delete rest.planning_llm_prompt_preview
  return rest
}

describe('normalizeProgress', () => {
  it('returns a typed snapshot for a valid payload', () => {
    const result = normalizeProgress(mockPlanningSnapshot)
    expect(stripLlmFields(result)).toMatchInlineSnapshot(`
      {
        "active_task_id": "",
        "assembly": {
          "all_parts_visible": false,
          "approved": false,
          "current_round": 0,
          "initial_placement_applied": false,
          "rounds": [],
          "status": "idle",
        },
        "completed_task_ids": [],
        "final_validation": {
          "capture_path": "",
          "detected_parts": [],
          "missing_critical_parts": [],
          "quantitative_metrics": [],
          "status": "pending",
          "viewpoint": "front",
        },
        "multi_expert_mode": true,
        "part_tasks": [],
        "stage": "planning",
        "stage_status": "running",
        "status": "running",
        "stop_reason": "",
        "task": "Build a wooden chair with a clean straight backrest.",
        "workflow_type": "multi_stage_modeling",
      }
    `)
  })

  it('returns default snapshot for null input', () => {
    expect(normalizeProgress(null)).toEqual(defaultProgress)
  })

  it('returns default snapshot for undefined input', () => {
    expect(normalizeProgress(undefined)).toEqual(defaultProgress)
  })

  it('returns default snapshot for empty object', () => {
    const result = normalizeProgress({})
    expect(stripLlmFields(result)).toEqual(stripLlmFields(defaultProgress))
  })

  it('fills defaults for a partial payload', () => {
    const result = normalizeProgress({ task: 'Build a chair', stage: 'planning' })
    expect(result.task).toBe('Build a chair')
    expect(result.stage).toBe('planning')
    // All other fields get defaults
    expect(result.status).toBe('idle')
    expect(result.stage_status).toBe('waiting_for_prompt')
    expect(result.active_task_id).toBe('')
    expect(result.completed_task_ids).toEqual([])
    expect(result.part_tasks).toEqual([])
    expect(result.stop_reason).toBe('')
    expect(result.assembly.status).toBe('pending')
    expect(result.final_validation.status).toBe('pending')
  })

  it('handles unknown stage gracefully without throwing', () => {
    const result = normalizeProgress({
      stage: 'unknown_pipeline_stage_42',
      stage_status: 'foo_bar',
      status: 'running',
    })
    expect(result.stage).toBe('unknown_pipeline_stage_42')
    expect(result.stage_status).toBe('foo_bar')
    expect(result.status).toBe('running')
    // No crash, all fields have sensible values
    expect(result.assembly).toBeDefined()
    expect(result.final_validation).toBeDefined()
    expect(Array.isArray(result.part_tasks)).toBe(true)
  })

  it('normalizes nested part_tasks and assembly from a complex payload', () => {
    const result = normalizeProgress(mockPartRefinementSnapshot)
    expect(result.part_tasks).toHaveLength(1)
    expect(result.part_tasks[0].task_id).toBe('chair_back')
    expect(result.part_tasks[0].status).toBe('running')
    expect(result.part_tasks[0].rounds).toHaveLength(1)
    expect(result.part_tasks[0].rounds[0].requested_action?.action_type).toBe('scale_axis_z')
    expect(result.assembly.status).toBe('idle')
    expect(result.active_task_id).toBe('chair_back')
  })

  it('preserves assembly approval identifiers needed for activity derivation', () => {
    const result = normalizeProgress({
      stage: 'completed',
      stage_status: 'completed',
      status: 'completed',
      assembly: {
        status: 'approved',
        current_round: 1,
        approved: true,
        all_parts_visible: true,
        initial_placement_applied: true,
        rounds: [
          {
            round_index: 1,
            task_id: 'seat',
            task_title: 'Seat',
            assembly_step_index: 1,
            capture_path: '',
            llm_prompt_preview: '',
            approved: true,
            feedback_summary: 'Assembly step approved',
            context: {},
            requested_actions: [],
          },
        ],
      },
    })

    expect(result.assembly.rounds).toHaveLength(1)
    expect(result.assembly.rounds[0].task_id).toBe('seat')
    expect(result.assembly.rounds[0].task_title).toBe('Seat')
    expect(result.assembly.rounds[0].assembly_step_index).toBe(1)
  })
})
