import type {
  AssemblyRoundRecord,
  MultiStageProgressSnapshot,
  PartRefinementRoundRecord,
  PartTaskProgress,
} from '../types'

export type InspectorSelection =
  | { kind: 'task'; task: PartTaskProgress }
  | { kind: 'part-round'; task: PartTaskProgress; round: PartRefinementRoundRecord }
  | { kind: 'assembly-round'; round: AssemblyRoundRecord }
  | null

export function defaultInspectorSelection(progress: MultiStageProgressSnapshot): InspectorSelection {
  const assemblyRounds = progress.assembly?.rounds ?? []
  const prefersAssembly =
    assemblyRounds.length > 0 &&
    (progress.stage === 'assembly' || progress.stage === 'completed' || progress.status === 'completed')
  if (prefersAssembly) {
    return { kind: 'assembly-round', round: assemblyRounds[assemblyRounds.length - 1] }
  }

  const activeTaskId = String(progress.active_task_id ?? '').trim()
  if (!activeTaskId) return null
  const selectedTask = progress.part_tasks.find((task) => task.task_id === activeTaskId)
  return selectedTask ? { kind: 'task', task: selectedTask } : null
}

export function getInspectorSelectionKind(selection: InspectorSelection): 'task' | 'part-round' | 'assembly-round' | 'none' {
  return selection?.kind ?? 'none'
}

export function getInspectorSelectedTask(selection: InspectorSelection): PartTaskProgress | null {
  if (!selection) return null
  if (selection.kind === 'task' || selection.kind === 'part-round') {
    return selection.task
  }
  return null
}

export function getInspectorSelectedTitle(selection: InspectorSelection) {
  if (!selection) return 'No active task selected'
  if (selection.kind === 'task' || selection.kind === 'part-round') {
    return selection.task.title
  }
  return `Assembly Round ${selection.round.round_index}`
}

export function getInspectorLatestCapturePath(selection: InspectorSelection) {
  if (!selection) return 'No capture selected'
  if (selection.kind === 'task') {
    return selection.task.rounds.at(-1)?.capture_path || 'No capture selected'
  }
  if (selection.kind === 'part-round') {
    return selection.round.capture_path || 'No capture selected'
  }
  return selection.round.capture_path || 'No capture selected'
}

export function buildInspectorBlocks(selection: InspectorSelection) {
  if (!selection) return []
  if (selection.kind === 'task') {
    return [
      {
        title: 'Task Summary',
        items: [
          { label: 'task_id', value: selection.task.task_id },
          { label: 'object_name', value: selection.task.object_name },
          { label: 'status', value: selection.task.status },
          { label: 'current_round', value: selection.task.current_round },
          { label: 'approved', value: String(selection.task.approved) },
        ],
      },
    ]
  }

  if (selection.kind === 'part-round') {
    return [
      {
        title: 'Round Summary',
        items: [
          { label: 'task', value: selection.task.title },
          { label: 'round_index', value: selection.round.round_index },
          { label: 'approved', value: String(selection.round.approved) },
          { label: 'viewpoint', value: selection.round.viewpoint },
          { label: 'feedback_summary', value: selection.round.feedback_summary },
        ],
      },
      {
        title: 'Context',
        items: Object.entries(selection.round.context).map(([label, value]) => ({ label, value })),
      },
      selection.round.requested_action
        ? {
            title: 'Requested Action',
            items: [
              { label: 'action_type', value: selection.round.requested_action.action_type },
              { label: 'execution_status', value: selection.round.requested_action.execution_status },
              { label: 'reason', value: selection.round.requested_action.reason },
              ...Object.entries(selection.round.requested_action.parameters).map(([label, value]) => ({
                label: `param.${label}`,
                value,
              })),
            ],
          }
        : {
            title: 'Requested Action',
            items: [{ label: 'state', value: 'No requested action for this round.' }],
          },
    ]
  }

  return [
    {
      title: 'Assembly Round',
      items: [
        { label: 'round_index', value: selection.round.round_index },
        { label: 'task_title', value: selection.round.task_title || 'Unknown' },
        { label: 'assembly_step_index', value: selection.round.assembly_step_index ?? 'Unknown' },
        { label: 'approved', value: String(selection.round.approved) },
        { label: 'feedback_summary', value: selection.round.feedback_summary },
      ],
    },
    {
      title: 'Context',
      items: Object.entries(selection.round.context).map(([label, value]) => ({ label, value })),
    },
    ...selection.round.requested_actions.map((action, index) => ({
      title: `Requested Action ${index + 1}`,
      items: [
        { label: 'action_type', value: action.action_type },
        { label: 'execution_status', value: action.execution_status },
        { label: 'reason', value: action.reason },
        ...Object.entries(action.parameters).map(([label, value]) => ({
          label: `param.${label}`,
          value,
        })),
      ],
    })),
  ]
}
