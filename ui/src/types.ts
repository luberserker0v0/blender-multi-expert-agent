export type WorkflowStatus = 'idle' | 'starting' | 'running' | 'completed' | 'failed' | 'stopping'

export interface ProgressActionRecord {
  action_type: string
  parameters: Record<string, unknown>
  reason: string
  execution_status: string
}

export interface ProgressContextRecord {
  current_mode: string
  active_object_name: string
  active_element_mode: string
}

export interface PartRefinementRoundRecord {
  round_index: number
  capture_path: string
  viewpoint: string
  capture_paths?: string[]
  viewpoints?: string[]
  llm_prompt_preview?: string
  approved: boolean
  feedback_summary: string
  context: ProgressContextRecord
  requested_action?: ProgressActionRecord | null
}

export interface PartTaskProgress {
  task_id: string
  title: string
  object_name: string
  status: string
  current_round: number
  approved: boolean
  hidden_after_approval: boolean
  rounds: PartRefinementRoundRecord[]
}

export interface AssemblyRoundRecord {
  round_index: number
  task_id?: string
  task_title?: string
  assembly_step_index?: number
  capture_path: string
  capture_paths?: string[]
  viewpoints?: string[]
  llm_prompt_preview?: string
  approved: boolean
  feedback_summary: string
  context: ProgressContextRecord
  requested_actions: ProgressActionRecord[]
}

export interface AssemblyProgress {
  status: string
  current_round: number
  approved: boolean
  all_parts_visible: boolean
  initial_placement_applied: boolean
  rounds: AssemblyRoundRecord[]
}

export interface FinalValidationSummary {
  status: string
  capture_path: string
  viewpoint: string
  detected_parts: string[]
  missing_critical_parts: string[]
  quantitative_metrics: Array<Record<string, unknown>>
}

export interface LlmPromptEventRecord {
  event_id: string
  stage: string
  label: string
  prompt_preview: string
  response_preview?: string
  validation_error?: string
  has_images: boolean
  image_count: number
}

export interface MeetingEvent {
  schema_version: number
  event_id: string
  phase: string
  kind:
    | 'phase_open'
    | 'proposal'
    | 'challenge'
    | 'response'
    | 'resolution'
    | 'phase_close'
    | 'build_step'
    | 'assemble_step'
    | 'validation_result'
  speaker?: string
  role?: string
  turn?: number
  round: number
  summary: string
  full_content: string
  content_preview?: string
  decision_refs?: string[]
  open_issue_refs?: string[]
  quality_flags?: string[]
  change_summary?: string
  substep?: 'scope' | 'analysis' | 'synthesis'
  final?: boolean
  deliberation_group_id?: string
  guardrail_flags?: string[]
  tool_calls?: McpToolCallRecord[]
  skipped?: boolean
  unresolved_planning_gap?: boolean
  missing_contract_fields?: string[]
  timestamp: string
  message: string
}

export interface MultiStageProgressSnapshot {
  workflow_type: string
  status: string
  task: string
  stage: string
  stage_status: string
  multi_expert_mode?: boolean
  planning_llm_prompt_preview?: string
  llm_prompt_events?: LlmPromptEventRecord[]
  active_task_id: string
  completed_task_ids: string[]
  part_tasks: PartTaskProgress[]
  assembly: AssemblyProgress
  final_validation: FinalValidationSummary
  stop_reason: string
}

export interface ActivityItem {
  id: string
  kind: 'user' | 'system' | 'status' | 'feedback' | 'llm' | 'meeting_phase' | 'meeting_step'
  title: string
  body: string
  timestamp: string
  collapsible?: boolean
  responseBody?: string
  validationError?: string
  pairKey?: string
  pairLabel?: string
  llmDirection?: 'prompt' | 'response'
  meetingSubstep?: 'scope' | 'analysis' | 'synthesis'
  meetingFinal?: boolean
  deliberationGroupId?: string
  guardrailFlags?: string[]
}

export interface WorkspaceDraft {
  taskInput: string
  referenceText: string
  referenceImages: string[]
}

export interface ActivityDerivationMarkers {
  lastStageSignature: string
  lastFeedbackSignature: string
  lastPlanSummarySignature: string
  lastCompletionSummarySignature: string
  lastFailureSummary: string
  lastRetryAttemptSignature: string
  seenPromptEventIds: string[]
  seenConclusionIds: string[]
}

export type ActivitySyncState = 'idle' | 'live' | 'stale' | 'resyncing'

export interface ActivitySyncMeta {
  lastServerCursor: string
  lastEventId: string
  syncState: ActivitySyncState
  markers: ActivityDerivationMarkers
}

export interface SessionStateSnapshot {
  session_id: string
  workspace: WorkspaceDraft
  activity: ActivityItem[]
  progress: MultiStageProgressSnapshot | null
  run_status: RunStatus
  retry_prompt: RetryPromptState
  console_log: string
  mcp_tool_calls: McpToolCallRecord[]
  mcp_status: McpConnectionStatus
  meeting_state?: Record<string, unknown> | null
  meeting_states?: Array<Record<string, unknown>>
  plan_artifact?: Record<string, unknown> | null
  build_execution_plan?: Record<string, unknown> | null
  assembly_execution_plan?: Record<string, unknown> | null
  failure_triage?: Record<string, unknown> | null
  server_cursor: string
  snapshot_generated_at: number
}

export interface ActivitySnapshotResponse extends SessionStateSnapshot {}

export interface BootstrapResponse {
  sessions: SessionSummary[]
  current_session_id: string
  settings: SavedSettings
  mcp_status?: McpConnectionStatus
}

export interface ActivityEventEnvelope {
  type: 'meeting_event' | 'snapshot_required' | 'activity_appended'
  session_id: string
  event_id: string
  sequence: number
  server_cursor: string
  data?: Record<string, unknown>
}

export interface SessionSummary {
  id: string
  title: string
  updatedAt: string
  unread?: boolean
}

export interface McpToolSummary {
  name: string
  description?: string
  inputSchema?: Record<string, unknown>
}

export interface McpConnectionStatus {
  enabled: boolean
  state: 'idle' | 'stale' | 'connecting' | 'connected' | 'failed'
  message: string
  tools: McpToolSummary[]
  server_name?: string
}

export interface McpToolCallRecord {
  timestamp: string
  session_id: string
  tool_name: string
  arguments: Record<string, unknown>
  is_error: boolean
  result: Record<string, unknown>
}

export interface RunStatus {
  session_id: string
  workflow_status: WorkflowStatus
  process_status: string
  error_message: string
  last_command: string[]
  pid: number | null
  exit_code: number | null
  attempt_index?: number | null
}

export interface LiveDiagnosticCheck {
  name: string
  ok: boolean
  message: string
  detail?: Record<string, unknown>
}

export interface LiveDiagnosticsResult {
  ok: boolean
  checks: LiveDiagnosticCheck[]
}

export interface AgentOrchestratorResult {
  name: string
  ok: boolean
  message: string
  detail?: Record<string, unknown>
}

export interface AgentOrchestratorModel {
  id: string
  provider: string
  model: string
}

export interface AgentOrchestratorModelsResult {
  ok: boolean
  models: AgentOrchestratorModel[]
  message: string
}

export interface RetryPromptState {
  show: boolean
  session_id: string
  remaining_retries: number
  decision_state: string
  failure_reason: string
  failure_category?: string
  planning_summary?: string
  blocking_constraint_refs?: string[]
  interaction_id?: string
  attempt_index?: number
  next_attempt_index?: number
  auto_retrying?: boolean
}

export interface SavedSettings {
  agentOrchestratorUrl: string
  agentOrchestratorModel: string
  keepAgentOrchestratorConversation: boolean
  agentOrchestratorTimeoutSeconds: number
  maxPartRefinementRounds: number
  maxAssemblyRounds: number
  useYoloValidation: boolean
  yoloModelPath: string
  yoloViewpoints: string
}
