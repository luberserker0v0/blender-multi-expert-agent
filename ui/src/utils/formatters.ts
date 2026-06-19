import type { ActivityItem, MultiStageProgressSnapshot, RunStatus, RetryPromptState } from '../types'

export function timeLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function text(value: unknown) {
  return typeof value === 'string' ? value : String(value ?? '')
}

export function createSessionId() {
  return `gui-${new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-')}-${crypto.randomUUID().slice(0, 6)}`
}

export function bubbleClass(kind: ActivityItem['kind']) {
  if (kind === 'user') return 'ml-auto max-w-3xl rounded-[24px] bg-slate-900 px-4 py-3 text-white shadow-sm'
  if (kind === 'feedback')
    return 'max-w-3xl rounded-[24px] bg-cyan-50 px-4 py-3 text-cyan-950 ring-1 ring-cyan-100 shadow-sm'
  if (kind === 'status')
    return 'max-w-3xl rounded-[24px] bg-amber-50 px-4 py-3 text-amber-950 ring-1 ring-amber-100 shadow-sm'
  if (kind === 'meeting_phase')
    return 'max-w-3xl border-t border-white/10 pt-4 pb-2'
  if (kind === 'meeting_step')
    return 'max-w-3xl rounded-[16px] bg-white/40 px-3 py-2 text-sm text-white ring-1 ring-white/5'
  return 'max-w-3xl rounded-[24px] bg-white/85 px-4 py-3 text-slate-800 ring-1 ring-white shadow-sm'
}

export function stripLlmPromptPrefix(value: string) {
  if (value.startsWith('我會給 AO 看 > ')) return value.slice('我會給 AO 看 > '.length)
  if (value.startsWith('AO 的回覆是 > ')) return value.slice('AO 的回覆是 > '.length)
  if (value.startsWith('我會給 LLM 看 > ')) return value.slice('我會給 LLM 看 > '.length)
  if (value.startsWith('LLM 的回覆是 > ')) return value.slice('LLM 的回覆是 > '.length)
  return value
}

export function isLlmResponseItem(value: string) {
  return value.startsWith('AO 的回覆是 > ') || value.startsWith('LLM 的回覆是 > ')
}

export function extractLlmPromptHeader(value: string) {
  const [firstLine] = value.split('\n')
  return firstLine || '我會給 AO 看 >'
}

export function extractLlmPromptBody(value: string) {
  const normalized = stripLlmPromptPrefix(value)
  const separatorIndex = normalized.indexOf('\n\n')
  if (separatorIndex === -1) return normalized
  return normalized.slice(separatorIndex + 2).trim()
}

// ── Expert role config ────────────────────────────────────────────

export interface ExpertRoleConfig {
  icon: string
  color: string
}

export const EXPERT_ROLE_CONFIG: Record<string, ExpertRoleConfig> = {
  designer: { icon: '\u{1F3A8}', color: 'text-blue-600' },
  reviewer: { icon: '\u{1F50D}', color: 'text-amber-600' },
  specifier: { icon: '\u{1F4D0}', color: 'text-emerald-600' },
  planner: { icon: '\u{1F4CB}', color: 'text-violet-600' },
  builder: { icon: '\u{1F528}', color: 'text-orange-600' },
  inspector: { icon: '\u{2705}', color: 'text-rose-600' },
  moderator: { icon: '\u{1F3A4}', color: 'text-sky-600' },
}

export function getExpertRoleConfig(speaker?: string): ExpertRoleConfig {
  const key = (speaker ?? '').split(/\s[-–—·|]\s|繚/)[0]?.trim().toLowerCase() ?? ''
  return EXPERT_ROLE_CONFIG[key] ?? { icon: '\u{2699}\u{FE0F}', color: 'text-stone-500' }
}

// ── Phase name formatting ────────────────────────────────────────

const PHASE_NAME_MAP: Record<string, string> = {
  design: 'Design Phase',
  spec: 'Spec Phase',
  plan: 'Plan Phase',
  build: 'Build Phase',
  assemble: 'Builder Placement Phase',
  validate: 'Validate Phase',
}

export function formatPhaseName(phase: string): string {
  return PHASE_NAME_MAP[phase] ?? phase
}

export function formatLlmPromptLabel(
  event: NonNullable<MultiStageProgressSnapshot['llm_prompt_events']>[number],
) {
  const stageLabelMap: Record<string, string> = {
    planning: 'Planning',
    part_review: 'Part Review',
    assembly_review: 'Assembly Review',
  }
  const stageLabel = stageLabelMap[event.stage] ?? 'Agent Prompt'
  const eventLabel = text(event.label).trim()
  const label = eventLabel ? ` - ${eventLabel}` : ''
  const imageLabel = event.has_images ? ` - ${event.image_count} images` : ''
  return `${stageLabel}${label}${imageLabel}`
}

export function formatLlmPairLabel(
  event: NonNullable<MultiStageProgressSnapshot['llm_prompt_events']>[number],
) {
  const compactId = event.event_id.replace(/^llm_prompt_/, '#')
  return `${compactId} - ${event.stage || 'agent'}`
}

export function formatPendingAction(
  event: NonNullable<MultiStageProgressSnapshot['llm_prompt_events']>[number],
) {
  const label = text(event.label).trim().toLowerCase()
  if (event.stage === 'planning' && label === 'plan_skeleton') {
    return '待會要做的事：先請 Agent Orchestrator 拆解建模任務，確認要做哪些 parts。'
  }
  if (event.stage === 'planning' && label.startsWith('task_detail:')) {
    return '待會要做的事：請 Agent Orchestrator 補完整個 part 的細節規格。'
  }
  if (event.stage === 'planning' && label === 'task_objects') {
    return '待會要做的事：請 Agent Orchestrator 規劃 task object 與建立政策。'
  }
  if (event.stage === 'part_review') {
    return '待會要做的事：請 Agent Orchestrator 檢查這個 part 的多視角結果，決定下一步修改。'
  }
  if (event.stage === 'assembly_review') {
    return '待會要做的事：請 Agent Orchestrator 檢查這個 assembly step 的位置、旋轉與縮放是否正確。'
  }
  return '待會要做的事：請 Agent Orchestrator 協助判斷下一步。'
}

export function formatStageActivityMessage(progress: MultiStageProgressSnapshot) {
  const activeTaskSuffix = progress.active_task_id ? ` | active task: ${progress.active_task_id}` : ''

  if (progress.stage === 'planning' && progress.stage_status === 'running') {
    return `規劃階段進行中：Agent 正在拆解任務與建立 parts spec${activeTaskSuffix}`
  }
  if (progress.stage === 'planning' && progress.stage_status === 'completed') {
    return '規劃階段已收斂：Agent 正在整理 Agent Orchestrator 的規劃結果。'
  }
  if (progress.stage === 'part_refinement' && progress.stage_status === 'running') {
    return `零件修正階段進行中：Agent 正在處理當前 part${activeTaskSuffix}`
  }
  if (progress.stage === 'assembly' && progress.stage_status === 'running') {
    return `組裝階段進行中：Agent 正在逐步放置與檢查 parts${activeTaskSuffix}`
  }
  if (progress.stage === 'final_validation' && progress.stage_status === 'running') {
    return '最終驗證階段進行中：Agent 正在準備成品檢查。'
  }
  if (progress.stage === 'completed' && progress.stage_status === 'completed') {
    return '整體流程已完成：Agent 正在整理最終結果。'
  }
  if (progress.stage_status === 'failed') {
    return `流程中斷：${progress.stop_reason || `${progress.stage} failed`}`
  }

  return progress.active_task_id
    ? `${progress.stage} / ${progress.stage_status} | active task: ${progress.active_task_id}`
    : `${progress.stage} / ${progress.stage_status}`
}

export function formatFailureSummary(
  progress: MultiStageProgressSnapshot,
  runStatus: RunStatus,
  retryPrompt: RetryPromptState,
) {
  if (retryPrompt.show) {
    return ''
  }
  if (retryPrompt.auto_retrying) {
    const nextAttempt = retryPrompt.next_attempt_index ?? (runStatus.attempt_index ?? 0) + 1
    return `這次執行失敗，Agent 正在準備從第 ${nextAttempt} 次 attempt 自動重試。`
  }
  if (progress.status === 'failed' || progress.stage_status === 'failed') {
    const reason = text(progress.stop_reason).trim()
    if (reason) {
      return `整個任務失敗。原因：${reason}`
    }
  }
  if (runStatus.workflow_status === 'failed') {
    const reason =
      text(runStatus.error_message).trim() ||
      (runStatus.exit_code !== null ? `Process exited with code ${runStatus.exit_code}.` : '')
    if (reason) {
      return `整個任務失敗。原因：${reason}`
    }
    return '整個任務失敗。原因：後端流程異常結束。'
  }
  return ''
}

/* ── Timestamp / session helpers (shared by normalizers and App) ── */

export function formatTimestamp(value: unknown) {
  if (typeof value === 'number') {
    return new Date(value * 1000).toLocaleString([], {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  }
  return typeof value === 'string' && value ? value : 'just now'
}

export function sortSessionUpdatedAt(value: string) {
  if (value === 'just now') return Number.MAX_SAFE_INTEGER
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

export function deriveSessionTitle(taskInput: string, referenceText: string, referenceImages: string[]) {
  return (
    text(taskInput).trim() ||
    (text(referenceText).trim()
      ? 'Reference-driven session'
      : referenceImages.length > 0
        ? 'Image reference session'
        : 'Untitled session')
  )
}

export function isGenericSessionTitle(value: string) {
  const normalized = text(value).trim().toLowerCase()
  return normalized === '' || normalized === 'untitled session' || normalized === 'new modeling session'
}
