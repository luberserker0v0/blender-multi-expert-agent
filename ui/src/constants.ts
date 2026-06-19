import type {
  ActivityDerivationMarkers,
  ActivityItem,
  ActivitySyncMeta,
  McpConnectionStatus,
  RetryPromptState,
  RunStatus,
  WorkspaceDraft,
} from './types'

export const EMPTY_ACTIVITY: ActivityItem[] = []

export const DEFAULT_MCP_STATUS: McpConnectionStatus = {
  enabled: true,
  state: 'idle',
  message: 'Blender MCP has not been initialized yet.',
  tools: [],
  server_name: '',
}

export const DEFAULT_RUN_STATUS: RunStatus = {
  session_id: '',
  workflow_status: 'idle',
  process_status: 'not_started',
  error_message: '',
  last_command: [],
  pid: null,
  exit_code: null,
  attempt_index: 0,
}

export const DEFAULT_RETRY_PROMPT: RetryPromptState = {
  show: false,
  session_id: '',
  remaining_retries: 0,
  decision_state: '',
  failure_reason: '',
  failure_category: '',
  planning_summary: '',
  blocking_constraint_refs: [],
  interaction_id: '',
  attempt_index: 0,
  next_attempt_index: 1,
  auto_retrying: false,
}

export const DEFAULT_WORKSPACE_DRAFT: WorkspaceDraft = {
  taskInput: '',
  referenceText: '',
  referenceImages: [],
}

export const DEFAULT_ACTIVITY_MARKERS: ActivityDerivationMarkers = {
  lastStageSignature: '',
  lastFeedbackSignature: '',
  lastPlanSummarySignature: '',
  lastCompletionSummarySignature: '',
  lastFailureSummary: '',
  lastRetryAttemptSignature: '',
  seenPromptEventIds: [],
  seenConclusionIds: [],
}

export const DEFAULT_ACTIVITY_SYNC_META: ActivitySyncMeta = {
  lastServerCursor: '',
  lastEventId: '',
  syncState: 'idle',
  markers: DEFAULT_ACTIVITY_MARKERS,
}
