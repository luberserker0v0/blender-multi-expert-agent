import type {
  ActivityItem,
  AssemblyProgress,
  FinalValidationSummary,
  MultiStageProgressSnapshot,
  
  RetryPromptState,
  RunStatus,
} from '../types'

// ---------------------------------------------------------------------------
// Helper: base empty assembly
// ---------------------------------------------------------------------------

const emptyAssembly: AssemblyProgress = {
  status: 'idle',
  current_round: 0,
  approved: false,
  all_parts_visible: false,
  initial_placement_applied: false,
  rounds: [],
}

const emptyFinalValidation: FinalValidationSummary = {
  status: 'pending',
  capture_path: '',
  viewpoint: 'front',
  detected_parts: [],
  missing_critical_parts: [],
  quantitative_metrics: [],
}

// ---------------------------------------------------------------------------
// MultiStageProgressSnapshot ??one per pipeline stage
// ---------------------------------------------------------------------------

export const mockIdleSnapshot: MultiStageProgressSnapshot = {
  workflow_type: 'multi_stage_modeling',
  status: 'idle',
  task: 'Build a wooden chair with a clean straight backrest.',
  stage: 'idle',
  stage_status: 'idle',
  active_task_id: '',
  completed_task_ids: [],
  stop_reason: '',
  part_tasks: [],
  assembly: emptyAssembly,
  final_validation: emptyFinalValidation,
}

export const mockPlanningSnapshot: MultiStageProgressSnapshot = {
  workflow_type: 'multi_stage_modeling',
  status: 'running',
  task: 'Build a wooden chair with a clean straight backrest.',
  stage: 'planning',
  stage_status: 'running',
  planning_llm_prompt_preview: 'Decompose the task "Build a wooden chair" into sub-tasks.',
  active_task_id: '',
  completed_task_ids: [],
  stop_reason: '',
  part_tasks: [],
  assembly: emptyAssembly,
  final_validation: emptyFinalValidation,
}

export const mockPartRefinementSnapshot: MultiStageProgressSnapshot = {
  workflow_type: 'multi_stage_modeling',
  status: 'running',
  task: 'Build a wooden chair with a clean straight backrest.',
  stage: 'part_refinement',
  stage_status: 'running',
  active_task_id: 'chair_back',
  completed_task_ids: [],
  stop_reason: '',
  part_tasks: [
    {
      task_id: 'chair_back',
      title: 'Chair Back',
      object_name: 'chair_back',
      status: 'running',
      current_round: 1,
      approved: false,
      hidden_after_approval: false,
      rounds: [
        {
          round_index: 1,
          capture_path: 'data/runtime/captures/chair_back_round_1.png',
          viewpoint: 'front',
          approved: false,
          feedback_summary: 'Initial backrest shape needs adjustment.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: {
            action_type: 'scale_axis_z',
            parameters: { factor: 1.5 },
            reason: 'Stretch the backrest upward.',
            execution_status: 'pending',
          },
        },
      ],
    },
  ],
  assembly: emptyAssembly,
  final_validation: emptyFinalValidation,
}

export const mockAssemblySnapshot: MultiStageProgressSnapshot = {
  workflow_type: 'multi_stage_modeling',
  status: 'running',
  task: 'Build a wooden chair with a clean straight backrest.',
  stage: 'assembly',
  stage_status: 'running',
  active_task_id: 'chair_seat',
  completed_task_ids: ['chair_back', 'chair_seat'],
  stop_reason: '',
  part_tasks: [
    {
      task_id: 'chair_back',
      title: 'Chair Back',
      object_name: 'chair_back',
      status: 'approved',
      current_round: 2,
      approved: true,
      hidden_after_approval: true,
      rounds: [
        {
          round_index: 1,
          capture_path: 'data/runtime/captures/chair_back_round_1.png',
          viewpoint: 'front',
          approved: false,
          feedback_summary: 'Backrest is too short and needs more vertical presence.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: {
            action_type: 'scale_axis_z',
            parameters: { factor: 1.5 },
            reason: 'Stretch the backrest upward.',
            execution_status: 'executed',
          },
        },
        {
          round_index: 2,
          capture_path: 'data/runtime/captures/chair_back_round_2.png',
          viewpoint: 'front',
          approved: true,
          feedback_summary: 'Backrest silhouette now feels balanced.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: null,
        },
      ],
    },
    {
      task_id: 'chair_seat',
      title: 'Chair Seat',
      object_name: 'chair_seat',
      status: 'approved',
      current_round: 1,
      approved: true,
      hidden_after_approval: true,
      rounds: [
        {
          round_index: 1,
          capture_path: 'data/runtime/captures/chair_seat_round_1.png',
          viewpoint: 'top',
          approved: true,
          feedback_summary: 'Seat proportions are acceptable for assembly.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_seat',
            active_element_mode: 'NONE',
          },
          requested_action: null,
        },
      ],
    },
  ],
  assembly: {
    status: 'running',
    current_round: 1,
    approved: false,
    all_parts_visible: true,
    initial_placement_applied: true,
    rounds: [
      {
        round_index: 1,
        capture_path: 'data/runtime/captures/assembly_round_1.png',
        approved: false,
        feedback_summary: 'Seat needs to shift slightly forward to align under the backrest.',
        context: {
          current_mode: 'OBJECT',
          active_object_name: 'chair_seat',
          active_element_mode: 'NONE',
        },
        requested_actions: [
          {
            action_type: 'move_object',
            parameters: { name: 'chair_seat', location: [0.0, 0.2, 0.4] },
            reason: 'Align the seat under the backrest.',
            execution_status: 'executed',
          },
        ],
      },
    ],
  },
  final_validation: {
    status: 'pending',
    capture_path: '',
    viewpoint: 'front',
    detected_parts: [],
    missing_critical_parts: [],
    quantitative_metrics: [],
  },
}

export const mockCompletedSnapshot: MultiStageProgressSnapshot = {
  workflow_type: 'multi_stage_modeling',
  status: 'completed',
  task: 'Build a wooden chair with a clean straight backrest.',
  stage: 'assembly',
  stage_status: 'completed',
  active_task_id: '',
  completed_task_ids: ['chair_back', 'chair_seat'],
  stop_reason: '',
  part_tasks: [
    {
      task_id: 'chair_back',
      title: 'Chair Back',
      object_name: 'chair_back',
      status: 'approved',
      current_round: 2,
      approved: true,
      hidden_after_approval: true,
      rounds: [
        {
          round_index: 1,
          capture_path: 'data/runtime/captures/chair_back_round_1.png',
          viewpoint: 'front',
          approved: false,
          feedback_summary: 'Backrest is too short and needs more vertical presence.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: {
            action_type: 'scale_axis_z',
            parameters: { factor: 1.5 },
            reason: 'Stretch the backrest upward.',
            execution_status: 'executed',
          },
        },
        {
          round_index: 2,
          capture_path: 'data/runtime/captures/chair_back_round_2.png',
          viewpoint: 'front',
          approved: true,
          feedback_summary: 'Backrest silhouette now feels balanced.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: null,
        },
      ],
    },
    {
      task_id: 'chair_seat',
      title: 'Chair Seat',
      object_name: 'chair_seat',
      status: 'approved',
      current_round: 1,
      approved: true,
      hidden_after_approval: true,
      rounds: [
        {
          round_index: 1,
          capture_path: 'data/runtime/captures/chair_seat_round_1.png',
          viewpoint: 'top',
          approved: true,
          feedback_summary: 'Seat proportions are acceptable for assembly.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_seat',
            active_element_mode: 'NONE',
          },
          requested_action: null,
        },
      ],
    },
  ],
  assembly: {
    status: 'completed',
    current_round: 1,
    approved: true,
    all_parts_visible: true,
    initial_placement_applied: true,
    rounds: [
      {
        round_index: 1,
        capture_path: 'data/runtime/captures/assembly_round_1.png',
        approved: true,
        feedback_summary: 'Assembly looks correct. All parts aligned.',
        context: {
          current_mode: 'OBJECT',
          active_object_name: 'chair_seat',
          active_element_mode: 'NONE',
        },
        requested_actions: [
          {
            action_type: 'move_object',
            parameters: { name: 'chair_seat', location: [0.0, 0.2, 0.4] },
            reason: 'Align the seat under the backrest.',
            execution_status: 'executed',
          },
        ],
      },
    ],
  },
  final_validation: {
    status: 'completed',
    capture_path: 'data/runtime/captures/final_validation.png',
    viewpoint: 'front',
    detected_parts: ['chair_back', 'chair_seat'],
    missing_critical_parts: [],
    quantitative_metrics: [
      { metric: 'alignment_score', value: 0.95 },
      { metric: 'coverage', value: 1.0 },
    ],
  },
}

export const mockFailedSnapshot: MultiStageProgressSnapshot = {
  workflow_type: 'multi_stage_modeling',
  status: 'failed',
  task: 'Build a wooden chair with a clean straight backrest.',
  stage: 'part_refinement',
  stage_status: 'failed',
  active_task_id: 'chair_back',
  completed_task_ids: [],
  stop_reason: 'Max refinement rounds reached without approval.',
  part_tasks: [
    {
      task_id: 'chair_back',
      title: 'Chair Back',
      object_name: 'chair_back',
      status: 'failed',
      current_round: 3,
      approved: false,
      hidden_after_approval: false,
      rounds: [
        {
          round_index: 1,
          capture_path: 'data/runtime/captures/chair_back_round_1.png',
          viewpoint: 'front',
          approved: false,
          feedback_summary: 'Backrest is too short.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: {
            action_type: 'scale_axis_z',
            parameters: { factor: 1.5 },
            reason: 'Stretch the backrest upward.',
            execution_status: 'executed',
          },
        },
        {
          round_index: 2,
          capture_path: 'data/runtime/captures/chair_back_round_2.png',
          viewpoint: 'front',
          approved: false,
          feedback_summary: 'Backrest is now too wide.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: {
            action_type: 'scale_axis_x',
            parameters: { factor: 0.8 },
            reason: 'Narrow the backrest width.',
            execution_status: 'executed',
          },
        },
        {
          round_index: 3,
          capture_path: 'data/runtime/captures/chair_back_round_3.png',
          viewpoint: 'front',
          approved: false,
          feedback_summary: 'Proportions still not balanced.',
          context: {
            current_mode: 'OBJECT',
            active_object_name: 'chair_back',
            active_element_mode: 'NONE',
          },
          requested_action: null,
        },
      ],
    },
  ],
  assembly: emptyAssembly,
  final_validation: emptyFinalValidation,
}

// ---------------------------------------------------------------------------
// ActivityItem ??one array per kind
// ---------------------------------------------------------------------------

export const mockUserActivities: ActivityItem[] = [
  {
    id: 'ua-1',
    kind: 'user',
    title: 'You',
    body: 'Build a wooden chair with a clean straight backrest, simple square seat, and light bevel feel.',
    timestamp: '09:41',
  },
  {
    id: 'ua-2',
    kind: 'user',
    title: 'You',
    body: 'Make the backrest slightly taller, about 1.5x the current height.',
    timestamp: '09:45',
  },
]

export const mockSystemActivities: ActivityItem[] = [
  {
    id: 'sa-1',
    kind: 'system',
    title: 'System',
    body: 'Session initialized.',
    timestamp: '09:40',
  },
  {
    id: 'sa-2',
    kind: 'system',
    title: 'System',
    body: 'Blender MCP connection established.',
    timestamp: '09:40',
    collapsible: true,
    responseBody: 'Connected to Blender MCP server at stdio.',
  },
  {
    id: 'sa-3',
    kind: 'system',
    title: 'System',
    body: 'Workflow started.',
    timestamp: '09:41',
  },
]

export const mockStatusActivities: ActivityItem[] = [
  {
    id: 'sta-1',
    kind: 'status',
    title: 'Status',
    body: 'planning / completed',
    timestamp: '09:42',
  },
  {
    id: 'sta-2',
    kind: 'status',
    title: 'Status',
    body: 'part_refinement / running | active task: chair_back',
    timestamp: '09:43',
  },
  {
    id: 'sta-3',
    kind: 'status',
    title: 'Status',
    body: 'assembly / running',
    timestamp: '09:46',
  },
]

export const mockFeedbackActivities: ActivityItem[] = [
  {
    id: 'fa-1',
    kind: 'feedback',
    title: 'Feedback',
    body: 'Backrest is too short. Stretch the object upward before moving to the seat.',
    timestamp: '09:43',
  },
  {
    id: 'fa-2',
    kind: 'feedback',
    title: 'Feedback',
    body: 'Seat needs to shift slightly forward to align under the backrest.',
    timestamp: '09:47',
  },
]

export const mockLlmActivities: ActivityItem[] = [
  {
    id: 'la-1',
    kind: 'llm',
    title: 'Agent',
    body: 'Task decomposition requested.',
    timestamp: '09:41',
    collapsible: true,
    llmDirection: 'prompt',
    pairKey: 'llm-pair-1',
    pairLabel: 'Show response',
    responseBody: 'Decompose the task into sub-tasks: chair_back, chair_seat.',
  },
  {
    id: 'la-2',
    kind: 'llm',
    title: 'Agent',
    body: 'Refinement suggestion for chair_back.',
    timestamp: '09:44',
    collapsible: true,
    llmDirection: 'response',
    pairKey: 'llm-pair-2',
    pairLabel: 'Show prompt',
    responseBody: 'Scale the backrest along Z axis by 1.5.',
  },
  {
    id: 'la-3',
    kind: 'llm',
    title: 'Agent',
    body: 'Assembly review completed - no issues found.',
    timestamp: '09:48',
    collapsible: false,
    validationError: undefined,
  },
]

// ---------------------------------------------------------------------------
// RetryPromptState
// ---------------------------------------------------------------------------

export const mockRetryHidden: RetryPromptState = {
  show: false,
  session_id: 'gui-20260514-001',
  remaining_retries: 3,
  decision_state: 'idle',
  failure_reason: '',
}

export const mockRetryShowing: RetryPromptState = {
  show: true,
  session_id: 'gui-20260514-001',
  remaining_retries: 2,
  decision_state: 'awaiting_user',
  failure_reason: 'Part refinement failed after 3 rounds.',
  interaction_id: 'retry-int-001',
  attempt_index: 3,
  next_attempt_index: 4,
  auto_retrying: false,
}

export const mockRetryAutoRetrying: RetryPromptState = {
  show: true,
  session_id: 'gui-20260514-001',
  remaining_retries: 1,
  decision_state: 'auto_retrying',
  failure_reason: 'Assembly alignment check failed.',
  interaction_id: 'retry-int-002',
  attempt_index: 1,
  next_attempt_index: 2,
  auto_retrying: true,
}

// ---------------------------------------------------------------------------
// RunStatus
// ---------------------------------------------------------------------------

export const mockRunIdle: RunStatus = {
  session_id: 'gui-20260514-001',
  workflow_status: 'idle',
  process_status: 'not_started',
  error_message: '',
  last_command: [],
  pid: null,
  exit_code: null,
}

export const mockRunRunning: RunStatus = {
  session_id: 'gui-20260514-001',
  workflow_status: 'running',
  process_status: 'running',
  error_message: '',
  last_command: ['python', 'scripts/run_pipeline.py', '--task', 'Build a wooden chair'],
  pid: 12345,
  exit_code: null,
}

export const mockRunCompleted: RunStatus = {
  session_id: 'gui-20260514-001',
  workflow_status: 'completed',
  process_status: 'exited',
  error_message: '',
  last_command: ['python', 'scripts/run_pipeline.py', '--task', 'Build a wooden chair'],
  pid: 12345,
  exit_code: 0,
}

export const mockRunFailed: RunStatus = {
  session_id: 'gui-20260514-001',
  workflow_status: 'failed',
  process_status: 'exited',
  error_message: 'Max retries exceeded.',
  last_command: ['python', 'scripts/run_pipeline.py', '--task', 'Build a wooden chair'],
  pid: 12346,
  exit_code: 1,
  attempt_index: 3,
}
