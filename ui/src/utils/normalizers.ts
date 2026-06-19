import type {
  ActivityItem,
  ActivitySnapshotResponse,
  BootstrapResponse,
  LiveDiagnosticsResult,
  McpConnectionStatus,
  McpToolCallRecord,
  MultiStageProgressSnapshot,
  RetryPromptState,
  RunStatus,
  SavedSettings,
  SessionStateSnapshot,
  SessionSummary,
  WorkspaceDraft,
} from '../types'
import { toNonNegativeNumber, toPositiveNumber, toStringArray } from './validators'
import {
  DEFAULT_ACTIVITY_SYNC_META,
  DEFAULT_MCP_STATUS,
  DEFAULT_RETRY_PROMPT,
  DEFAULT_RUN_STATUS,
  DEFAULT_WORKSPACE_DRAFT,
  EMPTY_ACTIVITY,
} from '../constants'
import {
  formatTimestamp,
  sortSessionUpdatedAt,
  isGenericSessionTitle,
} from './formatters'

/* ── Progress / snapshot normalizers ── */

export function createEmptyProgress(): MultiStageProgressSnapshot {
  return {
    workflow_type: 'multi_stage_modeling',
    status: 'idle',
    task: '',
    stage: 'idle',
    stage_status: 'waiting_for_prompt',
    multi_expert_mode: true,
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
  }
}

export function normalizeProgress(raw: unknown): MultiStageProgressSnapshot {
  if (typeof raw !== 'object' || raw === null) {
    return createEmptyProgress()
  }

  const payload = raw as Record<string, unknown>
  const partTasks = Array.isArray(payload.part_tasks)
    ? payload.part_tasks
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map(normalizePartTask)
    : []

  const assemblyPayload =
    typeof payload.assembly === 'object' && payload.assembly !== null
      ? (payload.assembly as Record<string, unknown>)
      : {}

  const finalValidationPayload =
    typeof payload.final_validation === 'object' && payload.final_validation !== null
      ? (payload.final_validation as Record<string, unknown>)
      : {}

  return {
    workflow_type: String(payload.workflow_type ?? 'multi_stage_modeling'),
    status: String(payload.status ?? 'idle'),
    task: String(payload.task ?? ''),
    stage: String(payload.stage ?? 'idle'),
    stage_status: String(payload.stage_status ?? 'waiting_for_prompt'),
    multi_expert_mode: true,
    planning_llm_prompt_preview: String(payload.planning_llm_prompt_preview ?? ''),
    llm_prompt_events: Array.isArray(payload.llm_prompt_events)
      ? payload.llm_prompt_events
          .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map((item) => ({
            event_id: String(item.event_id ?? ''),
            stage: String(item.stage ?? ''),
            label: String(item.label ?? ''),
            prompt_preview: String(item.prompt_preview ?? ''),
            response_preview: String(item.response_preview ?? ''),
            validation_error: String(item.validation_error ?? ''),
            has_images: Boolean(item.has_images ?? false),
            image_count: toNonNegativeNumber(item.image_count, 0),
          }))
      : [],
    active_task_id: String(payload.active_task_id ?? ''),
    completed_task_ids: toStringArray(payload.completed_task_ids),
    part_tasks: partTasks,
    assembly: {
      status: String(assemblyPayload.status ?? 'pending'),
      current_round: toNonNegativeNumber(assemblyPayload.current_round, 0),
      approved: Boolean(assemblyPayload.approved ?? false),
      all_parts_visible: Boolean(assemblyPayload.all_parts_visible ?? false),
      initial_placement_applied: Boolean(assemblyPayload.initial_placement_applied ?? false),
      rounds: Array.isArray(assemblyPayload.rounds)
        ? assemblyPayload.rounds
            .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
            .map(normalizeAssemblyRound)
        : [],
    },
    final_validation: {
      status: String(finalValidationPayload.status ?? 'pending'),
      capture_path: String(finalValidationPayload.capture_path ?? ''),
      viewpoint: String(finalValidationPayload.viewpoint ?? 'front'),
      detected_parts: toStringArray(finalValidationPayload.detected_parts),
      missing_critical_parts: toStringArray(finalValidationPayload.missing_critical_parts),
      quantitative_metrics: Array.isArray(finalValidationPayload.quantitative_metrics)
        ? finalValidationPayload.quantitative_metrics.filter(
            (item): item is Record<string, unknown> => typeof item === 'object' && item !== null,
          )
        : [],
    },
    stop_reason: String(payload.stop_reason ?? ''),
  }
}

function normalizePartTask(raw: Record<string, unknown>) {
  return {
    task_id: String(raw.task_id ?? ''),
    title: String(raw.title ?? 'Untitled part'),
    object_name: String(raw.object_name ?? ''),
    status: String(raw.status ?? 'pending'),
    current_round: toNonNegativeNumber(raw.current_round, 0),
    approved: Boolean(raw.approved ?? false),
    hidden_after_approval: Boolean(raw.hidden_after_approval ?? false),
    rounds: Array.isArray(raw.rounds)
      ? raw.rounds
          .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map(normalizePartRound)
      : [],
  }
}

function normalizePartRound(raw: Record<string, unknown>) {
  const action =
    typeof raw.requested_action === 'object' && raw.requested_action !== null
      ? normalizeAction(raw.requested_action as Record<string, unknown>)
      : null
  return {
    round_index: toNonNegativeNumber(raw.round_index, 0),
    capture_path: String(raw.capture_path ?? ''),
    viewpoint: String(raw.viewpoint ?? ''),
    approved: Boolean(raw.approved ?? false),
    llm_prompt_preview: String(raw.llm_prompt_preview ?? ''),
    feedback_summary: String(raw.feedback_summary ?? ''),
    context: normalizeContext(raw.context),
    requested_action: action,
  }
}

function normalizeAssemblyRound(raw: Record<string, unknown>) {
  return {
    round_index: toNonNegativeNumber(raw.round_index, 0),
    task_id: String(raw.task_id ?? ''),
    task_title: String(raw.task_title ?? ''),
    assembly_step_index: toNonNegativeNumber(raw.assembly_step_index, 0),
    capture_path: String(raw.capture_path ?? ''),
    llm_prompt_preview: String(raw.llm_prompt_preview ?? ''),
    approved: Boolean(raw.approved ?? false),
    feedback_summary: String(raw.feedback_summary ?? ''),
    context: normalizeContext(raw.context),
    requested_actions: Array.isArray(raw.requested_actions)
      ? raw.requested_actions
          .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map(normalizeAction)
      : [],
  }
}

function normalizeContext(raw: unknown) {
  const payload = typeof raw === 'object' && raw !== null ? (raw as Record<string, unknown>) : {}
  return {
    current_mode: String(payload.current_mode ?? ''),
    active_object_name: String(payload.active_object_name ?? ''),
    active_element_mode: String(payload.active_element_mode ?? ''),
  }
}

function normalizeAction(raw: Record<string, unknown>) {
  return {
    action_type: String(raw.action_type ?? ''),
    parameters:
      typeof raw.parameters === 'object' && raw.parameters !== null
        ? (raw.parameters as Record<string, unknown>)
        : {},
    reason: String(raw.reason ?? ''),
    execution_status: String(raw.execution_status ?? 'pending'),
  }
}

/* ── MCP normalizers ── */

export function normalizeMcpStatus(raw: unknown): McpConnectionStatus {
  if (typeof raw !== 'object' || raw === null) return DEFAULT_MCP_STATUS
  const payload = raw as Record<string, unknown>
  return {
    enabled: Boolean(payload.enabled ?? true),
    state: normalizeMcpState(payload.state),
    message: String(payload.message ?? ''),
    server_name: String(payload.server_name ?? ''),
    tools: Array.isArray(payload.tools)
      ? payload.tools
          .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map((item) => ({
            name: String(item.name ?? item.tool ?? 'unknown_tool'),
            description: typeof item.description === 'string' ? item.description : '',
            inputSchema:
              typeof item.inputSchema === 'object' && item.inputSchema !== null
                ? (item.inputSchema as Record<string, unknown>)
                : undefined,
          }))
      : [],
  }
}

export function normalizeMcpToolCalls(raw: unknown): McpToolCallRecord[] {
  if (!Array.isArray(raw)) return []
  return raw
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      timestamp: String(item.timestamp ?? ''),
      session_id: String(item.session_id ?? ''),
      tool_name: String(item.tool_name ?? 'unknown_tool'),
      arguments:
        typeof item.arguments === 'object' && item.arguments !== null
          ? (item.arguments as Record<string, unknown>)
          : {},
      is_error: Boolean(item.is_error ?? false),
      result:
        typeof item.result === 'object' && item.result !== null ? (item.result as Record<string, unknown>) : {},
    }))
}

function normalizeMcpState(value: unknown): McpConnectionStatus['state'] {
  return value === 'stale' || value === 'connecting' || value === 'connected' || value === 'failed' || value === 'idle'
    ? value
    : 'idle'
}

/* ── Run status normalizers ── */

export function normalizeRunStatus(raw: unknown): RunStatus {
  if (typeof raw !== 'object' || raw === null) return DEFAULT_RUN_STATUS
  const payload = raw as Record<string, unknown>
  return {
    session_id: String(payload.session_id ?? ''),
    workflow_status: normalizeWorkflowStatus(payload.workflow_status),
    process_status: String(payload.process_status ?? 'not_started'),
    error_message: String(payload.error_message ?? ''),
    last_command: Array.isArray(payload.last_command) ? payload.last_command.map((item) => String(item)) : [],
    pid: typeof payload.pid === 'number' ? payload.pid : null,
    exit_code: typeof payload.exit_code === 'number' ? payload.exit_code : null,
    attempt_index: toNonNegativeNumber(payload.attempt_index, 0),
  }
}

function normalizeWorkflowStatus(value: unknown): RunStatus['workflow_status'] {
  return value === 'idle' ||
    value === 'starting' ||
    value === 'running' ||
    value === 'completed' ||
    value === 'failed' ||
    value === 'stopping'
    ? value
    : 'idle'
}

/* ── Console / retry / diagnostics normalizers ── */

export function normalizeConsoleLogPayload(raw: unknown) {
  if (typeof raw !== 'object' || raw === null) return ''
  const payload = raw as Record<string, unknown>
  return typeof payload.content === 'string' ? payload.content : ''
}

export function normalizeRetryPrompt(raw: unknown): RetryPromptState {
  if (typeof raw !== 'object' || raw === null) return DEFAULT_RETRY_PROMPT
  const payload = raw as Record<string, unknown>
  return {
    show: Boolean(payload.show ?? false),
    session_id: String(payload.session_id ?? ''),
    remaining_retries: toNonNegativeNumber(payload.remaining_retries, 0),
    decision_state: String(payload.decision_state ?? ''),
    failure_reason: String(payload.failure_reason ?? ''),
    interaction_id: String(payload.interaction_id ?? ''),
    attempt_index: toNonNegativeNumber(payload.attempt_index, 0),
    next_attempt_index: toNonNegativeNumber(payload.next_attempt_index, 1),
    auto_retrying: Boolean(payload.auto_retrying ?? false),
  }
}

export function normalizeLiveDiagnostics(raw: unknown): LiveDiagnosticsResult {
  if (typeof raw !== 'object' || raw === null) {
    return { ok: false, checks: [] }
  }
  const payload = raw as Record<string, unknown>
  return {
    ok: Boolean(payload.ok ?? false),
    checks: Array.isArray(payload.checks)
      ? payload.checks
          .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
          .map((item) => ({
            name: String(item.name ?? 'unknown_check'),
            ok: Boolean(item.ok ?? false),
            message: String(item.message ?? ''),
            detail:
              typeof item.detail === 'object' && item.detail !== null
                ? (item.detail as Record<string, unknown>)
                : undefined,
          }))
      : [],
  }
}

/* ── Activity / workspace normalizers ── */

const VALID_ACTIVITY_KINDS = new Set([
  'user', 'system', 'status', 'feedback', 'llm',
  'meeting_phase', 'meeting_step',
] as const satisfies ActivityItem['kind'][])

export function normalizeActivityKind(raw: unknown): ActivityItem['kind'] {
  return typeof raw === 'string' && VALID_ACTIVITY_KINDS.has(raw as ActivityItem['kind'])
    ? (raw as ActivityItem['kind'])
    : 'system'
}

export function reviveActivityItems(raw: unknown): ActivityItem[] {
  if (!Array.isArray(raw)) return EMPTY_ACTIVITY
  return raw
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      id: String(item.id ?? crypto.randomUUID()),
      kind: normalizeActivityKind(item.kind),
      title: String(item.title ?? 'System'),
      body: String(item.body ?? ''),
      timestamp: String(item.timestamp ?? ''),
      collapsible: Boolean(item.collapsible ?? false),
      responseBody: typeof item.responseBody === 'string' ? item.responseBody : undefined,
      validationError: typeof item.validationError === 'string' ? item.validationError : undefined,
      pairKey: typeof item.pairKey === 'string' ? item.pairKey : undefined,
      pairLabel: typeof item.pairLabel === 'string' ? item.pairLabel : undefined,
      llmDirection:
        item.llmDirection === 'prompt' || item.llmDirection === 'response' ? item.llmDirection : undefined,
    }))
}

export function normalizeWorkspaceDraft(raw: unknown): WorkspaceDraft | null {
  if (typeof raw !== 'object' || raw === null) return null
  const payload = raw as Record<string, unknown>
  return {
    taskInput: String(payload.taskInput ?? ''),
    referenceText: String(payload.referenceText ?? ''),
    referenceImages: toStringArray(payload.referenceImages),
  }
}

export function createEmptyWorkspaceDraft() {
  return { ...DEFAULT_WORKSPACE_DRAFT }
}

/* ── Session / settings mapping ── */

export function mapApiSessionToUi(payload: Record<string, unknown>): SessionSummary {
  return {
    id: String(payload.id ?? ''),
    title: String(payload.title ?? 'Untitled session'),
    updatedAt: formatTimestamp(payload.updatedAt),
  }
}

export function reviveSessions(raw: unknown, initialValue: SessionSummary[]) {
  if (!Array.isArray(raw)) return initialValue
  const sessions = raw
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      id: String(item.id ?? ''),
      title: String(item.title ?? 'Untitled session'),
      updatedAt: formatTimestamp(item.updatedAt),
      unread: Boolean(item.unread ?? false),
    }))
    .filter((item) => item.id)
  return sessions.length > 0 ? sessions : initialValue
}

export function reviveWorkspaceDrafts(
  raw: unknown,
  initialValue: Record<string, WorkspaceDraft>,
) {
  if (typeof raw !== 'object' || raw === null) return initialValue
  const entries = Object.entries(raw as Record<string, unknown>).flatMap(([sessionId, value]) => {
    if (!sessionId || typeof value !== 'object' || value === null) return []
    const payload = value as Record<string, unknown>
    return [
      [
        sessionId,
        {
          taskInput: String(payload.taskInput ?? ''),
          referenceText: String(payload.referenceText ?? ''),
          referenceImages: toStringArray(payload.referenceImages),
        },
      ] as const,
    ]
  })
  return Object.fromEntries(entries)
}

export function normalizeBootstrapResponse(raw: unknown, defaultSettings: SavedSettings): BootstrapResponse {
  if (typeof raw !== 'object' || raw === null) {
    return {
      sessions: [],
      current_session_id: '',
      settings: defaultSettings,
      mcp_status: DEFAULT_MCP_STATUS,
    }
  }

  const payload = raw as Record<string, unknown>
  const sessions = Array.isArray(payload.sessions)
    ? payload.sessions
        .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
        .map(mapApiSessionToUi)
    : []

  return {
    sessions,
    current_session_id: String(payload.current_session_id ?? ''),
    settings:
      typeof payload.settings === 'object' && payload.settings !== null
        ? mapApiSettingsToUi(payload.settings as Record<string, unknown>, defaultSettings)
        : defaultSettings,
    mcp_status: normalizeMcpStatus(payload.mcp_status),
  }
}

export function normalizeSessionStateSnapshot(raw: unknown): SessionStateSnapshot {
  if (typeof raw !== 'object' || raw === null) {
    return {
      session_id: '',
      workspace: createEmptyWorkspaceDraft(),
      activity: EMPTY_ACTIVITY,
      progress: createEmptyProgress(),
      run_status: DEFAULT_RUN_STATUS,
      retry_prompt: DEFAULT_RETRY_PROMPT,
      console_log: '',
      mcp_tool_calls: [],
      mcp_status: DEFAULT_MCP_STATUS,
      server_cursor: '',
      snapshot_generated_at: 0,
    }
  }

  const payload = raw as Record<string, unknown>
  return {
    session_id: String(payload.session_id ?? ''),
    workspace: normalizeWorkspaceDraft(payload.workspace) ?? createEmptyWorkspaceDraft(),
    activity: reviveActivityItems(payload.activity),
    progress:
      payload.progress === null || payload.progress === undefined
        ? createEmptyProgress()
        : normalizeProgress(payload.progress),
    run_status: normalizeRunStatus(payload.run_status),
    retry_prompt: normalizeRetryPrompt(payload.retry_prompt),
    console_log: normalizeConsoleLogPayload({ content: payload.console_log }),
    mcp_tool_calls: normalizeMcpToolCalls(payload.mcp_tool_calls),
    mcp_status: normalizeMcpStatus(payload.mcp_status),
    server_cursor: String(payload.server_cursor ?? ''),
    snapshot_generated_at: toNonNegativeNumber(payload.snapshot_generated_at, 0),
  }
}

export function normalizeActivitySnapshotResponse(raw: unknown): ActivitySnapshotResponse {
  return normalizeSessionStateSnapshot(raw)
}

export function createEmptyActivitySyncMeta() {
  return {
    ...DEFAULT_ACTIVITY_SYNC_META,
    markers: {
      ...DEFAULT_ACTIVITY_SYNC_META.markers,
      seenPromptEventIds: [],
      seenConclusionIds: [],
    },
  }
}

export function reviveCurrentSessionId(raw: unknown, initialValue: string) {
  return typeof raw === 'string' ? raw : initialValue
}

export function reviveSettings(raw: unknown, initialValue: SavedSettings): SavedSettings {
  if (typeof raw !== 'object' || raw === null) return initialValue
  const payload = raw as Record<string, unknown>
  return {
    agentOrchestratorUrl: String(payload.agentOrchestratorUrl ?? initialValue.agentOrchestratorUrl),
    agentOrchestratorModel: String(payload.agentOrchestratorModel ?? initialValue.agentOrchestratorModel),
    keepAgentOrchestratorConversation: Boolean(
      payload.keepAgentOrchestratorConversation ?? initialValue.keepAgentOrchestratorConversation,
    ),
    agentOrchestratorTimeoutSeconds: toPositiveNumber(
      payload.agentOrchestratorTimeoutSeconds,
      initialValue.agentOrchestratorTimeoutSeconds,
    ),
    maxPartRefinementRounds: toPositiveNumber(
      payload.maxPartRefinementRounds,
      initialValue.maxPartRefinementRounds,
    ),
    maxAssemblyRounds: toPositiveNumber(payload.maxAssemblyRounds, initialValue.maxAssemblyRounds),
    useYoloValidation: Boolean(payload.useYoloValidation ?? initialValue.useYoloValidation),
    yoloModelPath: String(payload.yoloModelPath ?? initialValue.yoloModelPath),
    yoloViewpoints: String(payload.yoloViewpoints ?? initialValue.yoloViewpoints),
  }
}

export function mapApiSettingsToUi(
  payload: Record<string, unknown>,
  defaultSettings: SavedSettings,
): SavedSettings {
  return {
    agentOrchestratorUrl: String(
      payload.agent_orchestrator_base_url ?? defaultSettings.agentOrchestratorUrl,
    ),
    agentOrchestratorModel: String(
      payload.agent_orchestrator_model ?? defaultSettings.agentOrchestratorModel,
    ),
    keepAgentOrchestratorConversation: !Boolean(
      payload.agent_orchestrator_destroy_on_finish ?? !defaultSettings.keepAgentOrchestratorConversation,
    ),
    agentOrchestratorTimeoutSeconds: Number(
      payload.agent_orchestrator_timeout_seconds ?? defaultSettings.agentOrchestratorTimeoutSeconds,
    ),
    maxPartRefinementRounds: Number(
      payload.max_part_refinement_rounds ?? defaultSettings.maxPartRefinementRounds,
    ),
    maxAssemblyRounds: Number(payload.max_assembly_rounds ?? defaultSettings.maxAssemblyRounds),
    useYoloValidation: Boolean(payload.use_yolo_perception ?? defaultSettings.useYoloValidation),
    yoloModelPath: String(payload.yolo_model_path ?? defaultSettings.yoloModelPath),
    yoloViewpoints: Array.isArray(payload.yolo_viewpoints)
      ? payload.yolo_viewpoints.map((item) => String(item)).join(', ')
      : defaultSettings.yoloViewpoints,
  }
}

export function mapUiSettingsToApi(settings: SavedSettings) {
  const yoloViewpoints = String(settings.yoloViewpoints ?? '')
  return {
    agent_orchestrator_base_url: String(settings.agentOrchestratorUrl ?? ''),
    agent_orchestrator_model: String(settings.agentOrchestratorModel ?? ''),
    agent_orchestrator_destroy_on_finish: !settings.keepAgentOrchestratorConversation,
    agent_orchestrator_timeout_seconds: settings.agentOrchestratorTimeoutSeconds,
    max_part_refinement_rounds: settings.maxPartRefinementRounds,
    max_assembly_rounds: settings.maxAssemblyRounds,
    use_yolo_perception: settings.useYoloValidation,
    yolo_model_path: String(settings.yoloModelPath ?? ''),
    yolo_viewpoints: yoloViewpoints
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  }
}

export function preferSessionSummary(localSession: SessionSummary | undefined, remoteSession: SessionSummary) {
  if (!localSession) return remoteSession
  const remoteGeneric = isGenericSessionTitle(remoteSession.title)
  const localGeneric = isGenericSessionTitle(localSession.title)
  return {
    ...remoteSession,
    title: remoteGeneric && !localGeneric ? localSession.title : remoteSession.title,
    updatedAt:
      sortSessionUpdatedAt(localSession.updatedAt) > sortSessionUpdatedAt(remoteSession.updatedAt)
        ? localSession.updatedAt
        : remoteSession.updatedAt,
  }
}

export function mergeSessions(localSessions: SessionSummary[], remoteSessions: SessionSummary[]) {
  const merged = new Map<string, SessionSummary>()
  for (const session of remoteSessions) {
    const localSession = localSessions.find((item) => item.id === session.id)
    merged.set(session.id, preferSessionSummary(localSession, session))
  }
  for (const session of localSessions) {
    if (!merged.has(session.id)) {
      merged.set(session.id, session)
    }
  }
  return Array.from(merged.values()).sort(
    (left, right) => sortSessionUpdatedAt(right.updatedAt) - sortSessionUpdatedAt(left.updatedAt),
  )
}

export function resolveCurrentSessionId(
  localCurrentSessionId: string,
  sessions: SessionSummary[],
  remoteCurrentSessionId: string,
) {
  if (localCurrentSessionId && sessions.some((session) => session.id === localCurrentSessionId)) {
    return localCurrentSessionId
  }
  if (remoteCurrentSessionId && sessions.some((session) => session.id === remoteCurrentSessionId)) {
    return remoteCurrentSessionId
  }
  return sessions[0]?.id ?? ''
}
