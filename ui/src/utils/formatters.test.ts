import { describe, it, expect } from 'vitest'
import {
  formatStageActivityMessage,
  formatFailureSummary,
  formatPendingAction,
} from './formatters'
import {
  mockIdleSnapshot,
  mockPlanningSnapshot,
  mockPartRefinementSnapshot,
  mockAssemblySnapshot,
  mockCompletedSnapshot,
  mockFailedSnapshot,
  mockRetryHidden,
  mockRetryShowing,
  mockRetryAutoRetrying,
  mockRunIdle,
  mockRunFailed,
} from '../test/fixtures'
import type { MultiStageProgressSnapshot, LlmPromptEventRecord } from '../types'

// ---------------------------------------------------------------------------
// formatStageActivityMessage — 9 combos
// ---------------------------------------------------------------------------

describe('formatStageActivityMessage', () => {
  it('returns planning running message', () => {
    expect(formatStageActivityMessage(mockPlanningSnapshot)).toBe(
      '規劃階段進行中：Agent 正在拆解任務與建立 parts spec',
    )
  })

  it('returns planning completed message', () => {
    const msg = formatStageActivityMessage({
      ...mockPlanningSnapshot,
      stage_status: 'completed' as const,
    })
    expect(msg).toBe('規劃階段已收斂：Agent 正在整理 Agent Orchestrator 的規劃結果。')
  })

  it('returns part_refinement running message with active task suffix', () => {
    const msg = formatStageActivityMessage(mockPartRefinementSnapshot)
    expect(msg).toBe(
      '零件修正階段進行中：Agent 正在處理當前 part | active task: chair_back',
    )
  })

  it('returns assembly running message with active task suffix', () => {
    const msg = formatStageActivityMessage(mockAssemblySnapshot)
    expect(msg).toBe(
      '組裝階段進行中：Agent 正在逐步放置與檢查 parts | active task: chair_seat',
    )
  })

  it('returns final_validation running message', () => {
    const msg = formatStageActivityMessage({
      ...mockPlanningSnapshot,
      stage: 'final_validation',
      stage_status: 'running',
    })
    expect(msg).toBe('最終驗證階段進行中：Agent 正在準備成品檢查。')
  })

  it('returns completed + completed message', () => {
    const progress: MultiStageProgressSnapshot = {
      ...mockCompletedSnapshot,
      stage: 'completed',
      stage_status: 'completed',
    }
    expect(formatStageActivityMessage(progress)).toBe(
      '整體流程已完成：Agent 正在整理最終結果。',
    )
  })

  it('returns failure message when stage_status is failed', () => {
    const msg = formatStageActivityMessage(mockFailedSnapshot)
    expect(msg).toBe('流程中斷：Max refinement rounds reached without approval.')
  })

  it('returns fallback with active task when no explicit match', () => {
    const progress: MultiStageProgressSnapshot = {
      ...mockIdleSnapshot,
      stage: 'custom_stage',
      stage_status: 'custom_status',
      active_task_id: 'obj_001',
    }
    expect(formatStageActivityMessage(progress)).toBe(
      'custom_stage / custom_status | active task: obj_001',
    )
  })

  it('returns fallback without active task when no explicit match and no active task', () => {
    const progress: MultiStageProgressSnapshot = {
      ...mockIdleSnapshot,
      stage: 'idle',
      stage_status: 'idle',
      active_task_id: '',
    }
    expect(formatStageActivityMessage(progress)).toBe('idle / idle')
  })
})

// ---------------------------------------------------------------------------
// formatFailureSummary — 4 scenarios
// ---------------------------------------------------------------------------

describe('formatFailureSummary', () => {
  it('returns empty string when retry prompt is showing', () => {
    expect(formatFailureSummary(mockFailedSnapshot, mockRunIdle, mockRetryShowing)).toBe('')
  })

  it('returns auto-retry message when auto_retrying is true', () => {
    const retryPrompt = { ...mockRetryAutoRetrying, show: false }
    const msg = formatFailureSummary(mockFailedSnapshot, mockRunFailed, retryPrompt)
    expect(msg).toContain('自動重試')
    expect(msg).toContain('第 2 次')
  })

  it('returns failure message with stop_reason when progress is failed', () => {
    const msg = formatFailureSummary(mockFailedSnapshot, mockRunIdle, mockRetryHidden)
    expect(msg).toBe('整個任務失敗。原因：Max refinement rounds reached without approval.')
  })

  it('returns failure message from runStatus when workflow_status is failed and no progress failure', () => {
    const nonFailedProgress: MultiStageProgressSnapshot = {
      ...mockIdleSnapshot,
      status: 'running',
      stage_status: 'running',
    }
    const msg = formatFailureSummary(nonFailedProgress, mockRunFailed, mockRetryHidden)
    expect(msg).toBe('整個任務失敗。原因：Max retries exceeded.')
  })
})

// ---------------------------------------------------------------------------
// formatPendingAction — 5 LLM event types
// ---------------------------------------------------------------------------

function makeEvent(overrides: Partial<LlmPromptEventRecord>): LlmPromptEventRecord {
  return {
    event_id: 'llm_prompt_001',
    stage: '',
    label: '',
    prompt_preview: '',
    response_preview: '',
    validation_error: '',
    has_images: false,
    image_count: 0,
    ...overrides,
  }
}

describe('formatPendingAction', () => {
  it('returns planning plan_skeleton message', () => {
    expect(formatPendingAction(makeEvent({ stage: 'planning', label: 'plan_skeleton' }))).toBe(
      '待會要做的事：先請 Agent Orchestrator 拆解建模任務，確認要做哪些 parts。',
    )
  })

  it('returns planning task_detail message', () => {
    expect(
      formatPendingAction(makeEvent({ stage: 'planning', label: 'task_detail:chair_back' })),
    ).toBe('待會要做的事：請 Agent Orchestrator 補完整個 part 的細節規格。')
  })

  it('returns planning task_objects message', () => {
    expect(formatPendingAction(makeEvent({ stage: 'planning', label: 'task_objects' }))).toBe(
      '待會要做的事：請 Agent Orchestrator 規劃 task object 與建立政策。',
    )
  })

  it('returns part_review message', () => {
    expect(
      formatPendingAction(makeEvent({ stage: 'part_review', label: 'some_label' })),
    ).toBe('待會要做的事：請 Agent Orchestrator 檢查這個 part 的多視角結果，決定下一步修改。')
  })

  it('returns assembly_review message', () => {
    expect(
      formatPendingAction(makeEvent({ stage: 'assembly_review', label: 'assembly_step' })),
    ).toBe('待會要做的事：請 Agent Orchestrator 檢查這個 assembly step 的位置、旋轉與縮放是否正確。')
  })

  it('returns default message for unknown stage/label', () => {
    expect(
      formatPendingAction(makeEvent({ stage: 'unknown_stage', label: '' })),
    ).toBe('待會要做的事：請 Agent Orchestrator 協助判斷下一步。')
  })
})
