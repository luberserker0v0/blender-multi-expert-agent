import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  activityItemsFromMeetingEvent,
  createInitialActivityMarkers,
  deriveActivityUpdatesFromProgress,
} from './activity'
import {
  mockAssemblySnapshot,
  mockCompletedSnapshot,
  mockFailedSnapshot,
  mockPlanningSnapshot,
  mockRetryAutoRetrying,
  mockRetryHidden,
  mockRunFailed,
  mockRunRunning,
} from '../test/fixtures'
import type { ActivityItem, MeetingEvent, MultiStageProgressSnapshot } from '../types'

function summarize(items: ActivityItem[]) {
  return items.map((item) => ({
    kind: item.kind,
    title: item.title,
    body: item.body,
    pairKey: item.pairKey,
    llmDirection: item.llmDirection,
  }))
}

function createPlanningCompletedSnapshot(): MultiStageProgressSnapshot {
  return {
    ...mockPlanningSnapshot,
    stage_status: 'completed',
    part_tasks: [
      {
        task_id: 'chair_back',
        title: 'Chair Back',
        object_name: 'chair_back',
        status: 'pending',
        current_round: 0,
        approved: false,
        hidden_after_approval: false,
        rounds: [],
      },
      {
        task_id: 'chair_seat',
        title: 'Chair Seat',
        object_name: 'chair_seat',
        status: 'pending',
        current_round: 0,
        approved: false,
        hidden_after_approval: false,
        rounds: [],
      },
    ],
  }
}

function createPromptSnapshot(): MultiStageProgressSnapshot {
  return {
    ...mockPlanningSnapshot,
    llm_prompt_events: [
      {
        event_id: 'prompt-1',
        stage: 'planning',
        label: 'plan_skeleton',
        prompt_preview: 'Break the chair into parts.',
        response_preview: 'Seat, backrest, and legs.',
        validation_error: 'Missing JSON fence.',
        has_images: false,
        image_count: 0,
      },
    ],
  }
}

function createMultiExpertPromptSnapshot(): MultiStageProgressSnapshot {
  return {
    ...createPromptSnapshot(),
    multi_expert_mode: true,
  }
}

function createCompletedSnapshotWithAssemblyApproval(): MultiStageProgressSnapshot {
  return {
    ...mockCompletedSnapshot,
    assembly: {
      ...mockCompletedSnapshot.assembly,
      rounds: mockCompletedSnapshot.assembly.rounds.map((round, index) => ({
        ...round,
        task_id: 'chair_seat',
        task_title: 'Chair Seat',
        assembly_step_index: index + 1,
      })),
    },
  }
}

describe('deriveActivityUpdatesFromProgress', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('dedupes prompt events when the same snapshot is replayed', () => {
    const first = deriveActivityUpdatesFromProgress(
      createPromptSnapshot(),
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )
    const replay = deriveActivityUpdatesFromProgress(
      createPromptSnapshot(),
      mockRunRunning,
      mockRetryHidden,
      first.markers,
    )

    expect(summarize(first.items)).toEqual([
      {
        kind: 'system',
        title: 'System',
        body: expect.stringContaining('Agent Orchestrator'),
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'llm',
        title: 'Agent',
        body: 'Prompt > Planning - plan_skeleton\n\nBreak the chair into parts.',
        pairKey: 'prompt-1',
        llmDirection: 'prompt',
      },
      {
        kind: 'llm',
        title: 'Agent',
        body: 'Response > Planning - plan_skeleton\n\nSeat, backrest, and legs.',
        pairKey: 'prompt-1',
        llmDirection: 'response',
      },
      {
        kind: 'system',
        title: 'System',
        body: 'Agent Orchestrator response format was invalid. Agent will retry. Reason: Missing JSON fence.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'status',
        title: 'Status',
        body: expect.any(String),
        pairKey: undefined,
        llmDirection: undefined,
      },
    ])
    expect(replay.items).toHaveLength(0)
  })

  it('suppresses prompt-derived activity in multi-expert mode', () => {
    const result = deriveActivityUpdatesFromProgress(
      createMultiExpertPromptSnapshot(),
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )

    expect(result.items.some((item) => item.body.startsWith('Prompt > '))).toBe(false)
    expect(result.items.some((item) => item.body.startsWith('Response > '))).toBe(false)
  })

  it('dedupes stage signatures and only emits a new status when the signature changes', () => {
    const first = deriveActivityUpdatesFromProgress(
      mockAssemblySnapshot,
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )
    const replay = deriveActivityUpdatesFromProgress(
      mockAssemblySnapshot,
      mockRunRunning,
      mockRetryHidden,
      first.markers,
    )
    const changed = deriveActivityUpdatesFromProgress(
      {
        ...mockAssemblySnapshot,
        active_task_id: 'chair_back',
      },
      mockRunRunning,
      mockRetryHidden,
      first.markers,
    )

    expect(first.items.some((item) => item.kind === 'status')).toBe(true)
    expect(replay.items.filter((item) => item.kind === 'status')).toHaveLength(0)
    expect(changed.items.filter((item) => item.kind === 'status')).toHaveLength(1)
  })

  it('does not emit a placeholder idle status for waiting-for-prompt progress', () => {
    const result = deriveActivityUpdatesFromProgress(
      {
        ...mockPlanningSnapshot,
        status: 'idle',
        stage: 'idle',
        stage_status: 'waiting_for_prompt',
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
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )

    expect(result.items).toHaveLength(0)
  })

  it('dedupes feedback and approval conclusions across snapshot replay', () => {
    const first = deriveActivityUpdatesFromProgress(
      createCompletedSnapshotWithAssemblyApproval(),
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )
    const replay = deriveActivityUpdatesFromProgress(
      createCompletedSnapshotWithAssemblyApproval(),
      mockRunRunning,
      mockRetryHidden,
      first.markers,
    )

    expect(first.items.filter((item) => item.kind === 'feedback')).toHaveLength(1)
    expect(first.items.filter((item) => item.body.startsWith('Part approved:'))).toHaveLength(2)
    expect(first.items.filter((item) => item.body.startsWith('Assembly step approved:'))).toHaveLength(1)
    expect(replay.items).toHaveLength(0)
  })

  it('emits planning, completion, failure, and auto-retry summaries only under the right conditions', () => {
    const planning = deriveActivityUpdatesFromProgress(
      createPlanningCompletedSnapshot(),
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )
    const completed = deriveActivityUpdatesFromProgress(
      createCompletedSnapshotWithAssemblyApproval(),
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )
    const failed = deriveActivityUpdatesFromProgress(
      mockFailedSnapshot,
      mockRunFailed,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )
    const retrying = deriveActivityUpdatesFromProgress(
      mockFailedSnapshot,
      {
        ...mockRunRunning,
        workflow_status: 'running',
        attempt_index: 2,
        session_id: 'gui-20260514-001',
      },
      {
        ...mockRetryAutoRetrying,
        show: false,
        auto_retrying: true,
        next_attempt_index: 2,
        decision_state: 'auto_retrying',
      },
      createInitialActivityMarkers(),
    )

    expect(planning.items.some((item) => item.body === 'Planning completed: 2 tasks - Chair Back, Chair Seat.')).toBe(true)
    expect(completed.items.some((item) => item.body === 'Modeling completed: approved 2 parts - Chair Back, Chair Seat. Final assembly and validation finished.')).toBe(true)
    expect(failed.items.some((item) => item.body.includes('Max refinement rounds reached without approval.'))).toBe(true)
    expect(retrying.items.some((item) => item.body === 'Auto retry in progress: currently on attempt 2.')).toBe(true)
  })

  it('keeps a stable ordered timeline for a planning -> execution -> completed happy path', () => {
    let markers = createInitialActivityMarkers()
    const timeline: ActivityItem[] = []

    for (const progress of [
      createPlanningCompletedSnapshot(),
      mockAssemblySnapshot,
      createCompletedSnapshotWithAssemblyApproval(),
    ]) {
      const result = deriveActivityUpdatesFromProgress(progress, mockRunRunning, mockRetryHidden, markers)
      timeline.push(...result.items)
      markers = result.markers
    }

    expect(summarize(timeline)).toEqual([
      {
        kind: 'status',
        title: 'Status',
        body: expect.any(String),
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'system',
        title: 'System',
        body: 'Planning completed: 2 tasks - Chair Back, Chair Seat.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'status',
        title: 'Status',
        body: expect.any(String),
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'feedback',
        title: 'Feedback',
        body: 'Seat needs to shift slightly forward to align under the backrest.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'system',
        title: 'System',
        body: 'Part approved: Chair Back passed review. The workflow will move to the next task.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'system',
        title: 'System',
        body: 'Part approved: Chair Seat passed review. The workflow will move to the next task.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'status',
        title: 'Status',
        body: expect.any(String),
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'feedback',
        title: 'Feedback',
        body: 'Assembly looks correct. All parts aligned.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'system',
        title: 'System',
        body: 'Assembly step approved: Chair Seat passed review and will continue to the next step.',
        pairKey: undefined,
        llmDirection: undefined,
      },
      {
        kind: 'system',
        title: 'System',
        body: 'Modeling completed: approved 2 parts - Chair Back, Chair Seat. Final assembly and validation finished.',
        pairKey: undefined,
        llmDirection: undefined,
      },
    ])
  })

  it('keeps a stable ordered timeline for validation failure -> auto retry -> completed', () => {
    const promptSnapshot = createPromptSnapshot()
    const retryingRun = {
      ...mockRunRunning,
      workflow_status: 'running' as const,
      attempt_index: 2,
      session_id: 'gui-20260514-001',
    }
    let markers = createInitialActivityMarkers()
    const first = deriveActivityUpdatesFromProgress(promptSnapshot, retryingRun, mockRetryHidden, markers)
    markers = first.markers
    const second = deriveActivityUpdatesFromProgress(
      mockFailedSnapshot,
      retryingRun,
      {
        ...mockRetryAutoRetrying,
        show: false,
        auto_retrying: true,
        next_attempt_index: 2,
        decision_state: 'auto_retrying',
      },
      markers,
    )
    markers = second.markers
    const third = deriveActivityUpdatesFromProgress(
      createCompletedSnapshotWithAssemblyApproval(),
      mockRunRunning,
      mockRetryHidden,
      markers,
    )
    const bodies = [...first.items, ...second.items, ...third.items].map((item) => item.body)

    expect(bodies).toContain('Agent Orchestrator response format was invalid. Agent will retry. Reason: Missing JSON fence.')
    expect(bodies.some((body) => body.includes('Max refinement rounds reached without approval.'))).toBe(true)
    expect(bodies).toContain('Auto retry in progress: currently on attempt 2.')
    expect(bodies).toContain('Modeling completed: approved 2 parts - Chair Back, Chair Seat. Final assembly and validation finished.')
  })

  it('keeps a stable ordered timeline for mixed task and assembly approvals', () => {
    const result = deriveActivityUpdatesFromProgress(
      createCompletedSnapshotWithAssemblyApproval(),
      mockRunRunning,
      mockRetryHidden,
      createInitialActivityMarkers(),
    )

    expect(
      result.items
        .filter((item) => item.body.includes('passed review'))
        .map((item) => item.body),
    ).toEqual([
      'Part approved: Chair Back passed review. The workflow will move to the next task.',
      'Part approved: Chair Seat passed review. The workflow will move to the next task.',
      'Assembly step approved: Chair Seat passed review and will continue to the next step.',
    ])
  })
})

describe('activityItemsFromMeetingEvent', () => {
  it('maps known meeting events to the expected activity kinds', () => {
    const cases: Array<[MeetingEvent, ActivityItem['kind']]> = [
      [
        {
          schema_version: 1,
          event_id: '1',
          phase: 'design',
          kind: 'phase_open',
          round: 0,
          summary: 'started',
          full_content: 'started',
          timestamp: '09:40',
          message: 'started',
        },
        'meeting_phase',
      ],
      [
        {
          schema_version: 1,
          event_id: '2',
          phase: 'design',
          kind: 'proposal',
          round: 1,
          message: 'Detailed message',
          summary: 'Preview',
          full_content: 'Detailed message',
          speaker: 'Designer',
          timestamp: '09:41',
        },
        'llm',
      ],
      [
        {
          schema_version: 1,
          event_id: '3',
          phase: 'design',
          kind: 'validation_result',
          round: 1,
          summary: 'Extracted',
          full_content: 'Extracted',
          timestamp: '09:42',
          message: 'Extracted',
        },
        'system',
      ],
      [
        {
          schema_version: 1,
          event_id: '4',
          phase: 'design',
          kind: 'phase_close',
          round: 1,
          summary: 'ended',
          full_content: 'ended',
          timestamp: '09:43',
          message: 'ended',
        },
        'meeting_phase',
      ],
      [
        {
          schema_version: 1,
          event_id: '5',
          phase: 'build',
          kind: 'build_step',
          round: 0,
          summary: 'Build step',
          full_content: 'Build step',
          timestamp: '09:44',
          message: 'Build step',
        },
        'meeting_step',
      ],
      [
        {
          schema_version: 1,
          event_id: '6',
          phase: 'assembly',
          kind: 'assemble_step',
          round: 0,
          summary: 'Assemble step',
          full_content: 'Assemble step',
          timestamp: '09:45',
          message: 'Assemble step',
        },
        'meeting_step',
      ],
    ]

    for (const [event, expectedKind] of cases) {
      const items = activityItemsFromMeetingEvent(event)
      expect(items).toHaveLength(1)
      expect(items[0].kind).toBe(expectedKind)
    }
  })

  it('uses readable meeting titles, summaries, and phase bodies', () => {
    const proposalItems = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'meeting-1',
      phase: 'design',
      kind: 'proposal',
      speaker: 'Designer',
      role: 'designer',
      round: 1,
      summary: 'Chair concept uses three part families.',
      full_content: 'Proposal:\nUse seat, legs, and backrest as the core part families.',
      timestamp: '09:40',
      message: 'Proposal:\nUse seat, legs, and backrest as the core part families.',
    })
    const phaseItems = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'phase-1',
      phase: 'plan',
      kind: 'phase_open',
      round: 0,
      summary: '',
      full_content: '',
      timestamp: '09:41',
      message: '',
    } as MeetingEvent)
    const validationItems = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'validation-1',
      phase: 'validate',
      kind: 'validation_result',
      round: 1,
      summary: 'Validation result:\nChair passed the final check.',
      full_content: 'Validation result:\nChair passed the final check.',
      timestamp: '09:42',
      message: 'Validation result:\nChair passed the final check.',
    } as MeetingEvent)

    expect(proposalItems).toEqual([
      expect.objectContaining({
        id: 'meeting-1',
        kind: 'llm',
        title: 'Designer - Proposal',
        body: 'Chair concept uses three part families.',
        responseBody: 'Proposal:\nUse seat, legs, and backrest as the core part families.',
      }),
    ])
    expect(phaseItems[0]).toEqual(
      expect.objectContaining({
        kind: 'meeting_phase',
        title: 'Plan Phase',
        body: 'Meeting opened',
      }),
    )
    expect(validationItems[0]).toEqual(
      expect.objectContaining({
        kind: 'system',
        body: 'Validation result:\nChair passed the final check.',
      }),
    )
  })

  it('renders delegated agent substeps as non-final activity items', () => {
    const items = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'delib-1',
      phase: 'plan',
      kind: 'proposal',
      speaker: 'Planner',
      role: 'planner',
      round: 1,
      substep: 'analysis',
      final: false,
      deliberation_group_id: 'plan:proposal:1:planner:2',
      summary: 'Check family set and builder placement boundary.',
      full_content: 'Analysis:\nCheck family set and builder placement boundary.',
      timestamp: '10:15',
      message: 'Analysis:\nCheck family set and builder placement boundary.',
    })

    expect(items).toEqual([
      expect.objectContaining({
        kind: 'llm',
        title: 'Planner - Analysis',
        body: 'Check family set and builder placement boundary.',
        meetingSubstep: 'analysis',
        meetingFinal: false,
        deliberationGroupId: 'plan:proposal:1:planner:2',
      }),
    ])
  })

  it('renders meeting skill summary as body while keeping full AO response expandable', () => {
    const items = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'summary-1',
      phase: 'design',
      kind: 'resolution',
      speaker: 'Moderator',
      role: 'moderator',
      round: 1,
      summary: '結論：接受單一 cube 設計。\n下一步：進入規格階段。',
      full_content:
        'Decision: Accept proposal.\n\nAccepted:\n- Use one cube part.\n\nRejected:\n- Face/edge/vertex decomposition.\n\nOpen Issues:\nNone',
      timestamp: '09:43',
      message: '結論：接受單一 cube 設計。',
    })

    expect(items).toEqual([
      expect.objectContaining({
        id: 'summary-1',
        kind: 'llm',
        title: 'Moderator - Resolution',
        body: '結論：接受單一 cube 設計。\n下一步：進入規格階段。',
        collapsible: true,
        responseBody:
          'Decision: Accept proposal.\n\nAccepted:\n- Use one cube part.\n\nRejected:\n- Face/edge/vertex decomposition.\n\nOpen Issues:\nNone',
      }),
    ])
  })

  it('renders skipped assemble steps as collapsible missing-field details without fake tool calls', () => {
    const items = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'assemble-skip-1',
      phase: 'assemble',
      kind: 'assemble_step',
      round: 2,
      summary: 'Skipped assembly for stem due to unresolved contract fields.',
      full_content: 'Skipped assembly for stem due to unresolved contract fields.',
      timestamp: '09:46',
      message: 'Skipped assembly for stem due to unresolved contract fields.',
      skipped: true,
      unresolved_planning_gap: true,
      missing_contract_fields: ['resolved_attachment_target_point', 'resolved_local_anchor_point'],
      tool_calls: [],
    })

    expect(items).toEqual([
      expect.objectContaining({
        kind: 'meeting_step',
        body: 'Skipped assembly for stem due to unresolved contract fields.',
        collapsible: true,
        responseBody:
          'Missing contract fields:\n- `resolved_attachment_target_point`\n- `resolved_local_anchor_point`',
      }),
    ])
  })

  it('returns an empty list for unknown meeting event kinds', () => {
    const items = activityItemsFromMeetingEvent({
      schema_version: 1,
      event_id: 'unknown-1',
      phase: 'design',
      kind: 'unknown_kind',
      round: 0,
      summary: 'ignored',
      full_content: 'ignored',
      timestamp: '09:43',
      message: 'ignored',
    } as unknown as MeetingEvent)

    expect(items).toEqual([])
  })
})
