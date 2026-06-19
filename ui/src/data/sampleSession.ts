import type {
  ActivityItem,
  MultiStageProgressSnapshot,
  SavedSettings,
  SessionSummary,
} from '../types'

export const defaultSettings: SavedSettings = {
  agentOrchestratorUrl: 'http://127.0.0.1:4111',
  agentOrchestratorModel: '',
  keepAgentOrchestratorConversation: false,
  agentOrchestratorTimeoutSeconds: 120,
  maxPartRefinementRounds: 3,
  maxAssemblyRounds: 3,
  useYoloValidation: true,
  yoloModelPath: 'D:\\models\\yolo\\yolo26s.pt',
  yoloViewpoints: 'front, side, top',
}

export const sampleSessions: SessionSummary[] = [
  {
    id: 'gui-20260514-001',
    title: 'Wooden chair with straight backrest',
    updatedAt: '2 min ago',
    unread: true,
  },
  {
    id: 'gui-20260513-204',
    title: 'Rounded stool exploration',
    updatedAt: 'Yesterday',
  },
  {
    id: 'gui-20260512-118',
    title: 'Desk lamp assembly review',
    updatedAt: 'May 12',
  },
]

export const sampleActivity: ActivityItem[] = [
  {
    id: 'a1',
    kind: 'user',
    title: 'You',
    body: 'Build a wooden chair with a clean straight backrest, simple square seat, and light bevel feel.',
    timestamp: '09:41',
  },
  {
    id: 'a2',
    kind: 'status',
    title: 'Status',
    body: 'planning / completed',
    timestamp: '09:42',
  },
  {
    id: 'a3',
    kind: 'status',
    title: 'Status',
    body: 'part_refinement / running | active task: chair_back',
    timestamp: '09:43',
  },
  {
    id: 'a4',
    kind: 'feedback',
    title: 'Feedback',
    body: 'Backrest is too short. Stretch the object upward before moving to the seat.',
    timestamp: '09:43',
  },
  {
    id: 'a5',
    kind: 'status',
    title: 'Status',
    body: 'assembly / running',
    timestamp: '09:46',
  },
]

export const sampleProgress: MultiStageProgressSnapshot = {
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
        capture_path: 'data/runtime/captures/gui-20260514-001_assembly_round_1.png',
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
            parameters: {
              name: 'chair_seat',
              location: [0.0, 0.2, 0.4],
            },
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
