import { DEFAULT_ACTIVITY_MARKERS } from '../constants'
import type {
  ActivityDerivationMarkers,
  ActivityItem,
  ActivitySyncMeta,
  MeetingEvent,
  MultiStageProgressSnapshot,
  RetryPromptState,
  RunStatus,
} from '../types'
import {
  formatFailureSummary,
  formatLlmPairLabel,
  formatLlmPromptLabel,
  formatPendingAction,
  formatPhaseName,
  formatStageActivityMessage,
  timeLabel,
} from '../utils/formatters'

type AppendableActivity = Omit<ActivityItem, 'id' | 'timestamp'> & Partial<Pick<ActivityItem, 'id' | 'timestamp'>>

export interface DeriveActivityResult {
  items: ActivityItem[]
  markers: ActivityDerivationMarkers
}

export function createInitialActivityMarkers(): ActivityDerivationMarkers {
  return {
    ...DEFAULT_ACTIVITY_MARKERS,
    seenPromptEventIds: [],
    seenConclusionIds: [],
  }
}

export function createEmptyActivitySyncMeta(): ActivitySyncMeta {
  return {
    lastServerCursor: '',
    lastEventId: '',
    syncState: 'idle',
    markers: createInitialActivityMarkers(),
  }
}

export function createActivityItem(item: AppendableActivity): ActivityItem {
  return {
    id: crypto.randomUUID(),
    timestamp: timeLabel(),
    ...item,
  }
}

function appendSystemItem(items: ActivityItem[], kind: ActivityItem['kind'], body: string, options?: Partial<ActivityItem>) {
  items.push(
    createActivityItem({
      id: options?.id,
      timestamp: options?.timestamp,
      kind,
      title: options?.title ?? defaultTitleForKind(kind),
      body,
      collapsible: options?.collapsible,
      responseBody: options?.responseBody,
      validationError: options?.validationError,
      pairKey: options?.pairKey,
      pairLabel: options?.pairLabel,
      llmDirection: options?.llmDirection,
      meetingSubstep: options?.meetingSubstep,
      meetingFinal: options?.meetingFinal,
      deliberationGroupId: options?.deliberationGroupId,
      guardrailFlags: options?.guardrailFlags,
    }),
  )
}

function defaultTitleForKind(kind: ActivityItem['kind']) {
  const titleMap: Record<ActivityItem['kind'], string> = {
    user: 'You',
    system: 'System',
    status: 'Status',
    feedback: 'Feedback',
    llm: 'Agent',
    meeting_phase: 'Phase',
    meeting_step: 'Step',
  }
  return titleMap[kind]
}

function text(value: unknown) {
  return typeof value === 'string' ? value : String(value ?? '')
}

function isPlaceholderIdleProgress(progress: MultiStageProgressSnapshot) {
  return (
    progress.status === 'idle' &&
    progress.stage === 'idle' &&
    progress.stage_status === 'waiting_for_prompt' &&
    !progress.active_task_id &&
    progress.part_tasks.length === 0 &&
    progress.completed_task_ids.length === 0 &&
    progress.assembly.current_round === 0 &&
    progress.assembly.rounds.length === 0 &&
    progress.final_validation.status === 'pending' &&
    !text(progress.stop_reason).trim()
  )
}

function isMultiExpertActivityMode(progress: MultiStageProgressSnapshot) {
  return Boolean(progress.multi_expert_mode)
}

function resolveMeetingEventSummary(event: MeetingEvent) {
  return text(event.summary).trim() || text(event.content_preview).trim() || text(event.message).trim()
}

function resolveMeetingEventFullContent(event: MeetingEvent) {
  return text(event.full_content).trim() || text(event.message).trim()
}

function formatMeetingEventToolCalls(event: MeetingEvent) {
  const toolCalls = Array.isArray(event.tool_calls) ? event.tool_calls : []
  if (toolCalls.length === 0) return ''
  return toolCalls
    .map((toolCall) => {
      const argumentsText = Object.entries(toolCall.arguments ?? {})
        .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
        .join(', ')
      return argumentsText
        ? `- \`${toolCall.tool_name}(${argumentsText})\``
        : `- \`${toolCall.tool_name}()\``
    })
    .join('\n')
}

function formatMissingContractFields(event: MeetingEvent) {
  const missingFields = Array.isArray(event.missing_contract_fields) ? event.missing_contract_fields : []
  if (missingFields.length === 0) return ''
  return ['Missing contract fields:', ...missingFields.map((field) => `- \`${field}\``)].join('\n')
}

function formatMeetingSpeakerTitle(event: MeetingEvent) {
  const speaker = text(event.speaker).trim() || (event.kind === 'resolution' ? 'Moderator' : 'Agent')
  if (event.final === false && event.substep) {
    return `${speaker} - ${event.substep[0].toUpperCase()}${event.substep.slice(1)}`
  }
  switch (event.kind) {
    case 'proposal':
      return `${speaker} - Proposal`
    case 'challenge':
      return `${speaker} - Challenge`
    case 'response':
      return `${speaker} - Response`
    case 'resolution':
      return `${speaker} - Resolution`
    default:
      return speaker
  }
}

function formatMeetingPhaseBody(event: MeetingEvent) {
  const kind = String(event.kind)
  const summary = resolveMeetingEventSummary(event)
  if (summary) return summary
  if (kind === 'phase_start' || kind === 'phase_open') return 'Meeting opened'
  if (kind === 'phase_end' || kind === 'phase_close') return 'Meeting closed'
  return ''
}

export function deriveActivityUpdatesFromProgress(
  progress: MultiStageProgressSnapshot,
  runStatus: RunStatus,
  retryPrompt: RetryPromptState,
  markers: ActivityDerivationMarkers,
): DeriveActivityResult {
  const nextMarkers: ActivityDerivationMarkers = {
    ...markers,
    seenPromptEventIds: [...markers.seenPromptEventIds],
    seenConclusionIds: [...markers.seenConclusionIds],
  }
  const items: ActivityItem[] = []
  const signature = `${progress.status}|${progress.stage}|${progress.stage_status}|${progress.active_task_id}`
  const shouldSuppressPlaceholderIdle = isPlaceholderIdleProgress(progress)
  const multiExpertMode = isMultiExpertActivityMode(progress)

  if (!multiExpertMode) {
    for (const event of progress.llm_prompt_events ?? []) {
      if (!event.event_id || nextMarkers.seenPromptEventIds.includes(event.event_id)) continue
      nextMarkers.seenPromptEventIds.push(event.event_id)
      const pairLabel = formatLlmPairLabel(event)
      appendSystemItem(items, 'system', formatPendingAction(event))
      appendSystemItem(items, 'llm', `Prompt > ${formatLlmPromptLabel(event)}\n\n${event.prompt_preview}`, {
        collapsible: true,
        validationError: event.validation_error ?? '',
        pairKey: event.event_id,
        pairLabel,
        llmDirection: 'prompt',
      })
      if (text(event.response_preview).trim()) {
        appendSystemItem(items, 'llm', `Response > ${formatLlmPromptLabel(event)}\n\n${event.response_preview}`, {
          collapsible: true,
          pairKey: event.event_id,
          pairLabel,
          llmDirection: 'response',
        })
      }
      const validationError = text(event.validation_error).trim()
      if (validationError) {
        appendSystemItem(items, 'system', `Agent Orchestrator response format was invalid. Agent will retry. Reason: ${validationError}`)
      }
    }
  }

  if (!multiExpertMode && !shouldSuppressPlaceholderIdle && signature !== nextMarkers.lastStageSignature) {
    nextMarkers.lastStageSignature = signature
    const stageMessage = formatStageActivityMessage(progress)
    if (stageMessage) {
      appendSystemItem(items, 'status', stageMessage)
    }
  }

  const latestFeedback =
    progress.stage === 'assembly'
      ? progress.assembly.rounds.at(-1)?.feedback_summary ?? ''
      : progress.part_tasks.find((task) => task.task_id === progress.active_task_id)?.rounds.at(-1)?.feedback_summary ?? ''
  if (!multiExpertMode && latestFeedback && latestFeedback !== nextMarkers.lastFeedbackSignature) {
    nextMarkers.lastFeedbackSignature = latestFeedback
    appendSystemItem(items, 'feedback', latestFeedback)
  }

  if (!multiExpertMode) {
    emitTaskConclusions(progress, nextMarkers, items)
  }

  const planTaskLabels = progress.part_tasks
    .map((task) => text(task.title).trim() || text(task.task_id).trim())
    .filter(Boolean)
  const planSummarySignature = `${progress.stage}|${progress.stage_status}|${planTaskLabels.join('|')}`
  if (
    !multiExpertMode &&
    progress.stage === 'planning' &&
    progress.stage_status === 'completed' &&
    planTaskLabels.length > 0 &&
    planSummarySignature !== nextMarkers.lastPlanSummarySignature
  ) {
    nextMarkers.lastPlanSummarySignature = planSummarySignature
    appendSystemItem(items, 'system', `Planning completed: ${planTaskLabels.length} tasks - ${planTaskLabels.join(', ')}.`)
  }

  const completedTaskLabels = progress.part_tasks
    .filter((task) => task.approved)
    .map((task) => text(task.title).trim() || text(task.task_id).trim())
    .filter(Boolean)
  const completionSummarySignature = `${progress.status}|${progress.stop_reason}|${completedTaskLabels.join('|')}`
  if (
    progress.status === 'completed' &&
    completedTaskLabels.length > 0 &&
    completionSummarySignature !== nextMarkers.lastCompletionSummarySignature
  ) {
    nextMarkers.lastCompletionSummarySignature = completionSummarySignature
    appendSystemItem(
      items,
      'system',
      `Modeling completed: approved ${completedTaskLabels.length} parts - ${completedTaskLabels.join(', ')}. Final assembly and validation finished.`,
    )
  }

  const failureSummary = formatFailureSummary(progress, runStatus, retryPrompt)
  if (failureSummary && failureSummary !== nextMarkers.lastFailureSummary) {
    nextMarkers.lastFailureSummary = failureSummary
    appendSystemItem(items, 'system', failureSummary)
  }

  if (retryPrompt.auto_retrying) {
    const attemptIndex = runStatus.attempt_index ?? retryPrompt.next_attempt_index ?? 0
    const retrySignature = `${runStatus.session_id}:${attemptIndex}:${retryPrompt.decision_state}`
    if (
      attemptIndex > 1 &&
      runStatus.workflow_status === 'running' &&
      retrySignature !== nextMarkers.lastRetryAttemptSignature
    ) {
      nextMarkers.lastRetryAttemptSignature = retrySignature
      appendSystemItem(items, 'status', `Auto retry in progress: currently on attempt ${attemptIndex}.`)
    }
  }

  return { items, markers: nextMarkers }
}

function emitTaskConclusions(
  progress: MultiStageProgressSnapshot,
  markers: ActivityDerivationMarkers,
  items: ActivityItem[],
) {
  for (const task of progress.part_tasks) {
    if (!task.approved) continue
    const eventId = `part-approved:${task.task_id}`
    if (markers.seenConclusionIds.includes(eventId)) continue
    markers.seenConclusionIds.push(eventId)
    appendSystemItem(items, 'system', `Part approved: ${task.title} passed review. The workflow will move to the next task.`)
  }

  for (const round of progress.assembly.rounds) {
    if (!round.approved || !round.task_id) continue
    const eventId = `assembly-approved:${round.task_id}:${round.assembly_step_index ?? 0}`
    if (markers.seenConclusionIds.includes(eventId)) continue
    markers.seenConclusionIds.push(eventId)
    appendSystemItem(
      items,
      'system',
      `Assembly step approved: ${round.task_title || round.task_id} passed review and will continue to the next step.`,
    )
  }
}

export function activityItemsFromMeetingEvent(event: MeetingEvent): ActivityItem[] {
  const items: ActivityItem[] = []
  const fullContent = resolveMeetingEventFullContent(event)
  const summary = resolveMeetingEventSummary(event)
  switch (String(event.kind)) {
    case 'phase_start':
    case 'phase_open':
      appendSystemItem(items, 'meeting_phase', formatMeetingPhaseBody(event), {
        id: event.event_id,
        title: formatPhaseName(event.phase),
      })
      break
    case 'expert_spoke':
    case 'proposal':
    case 'challenge':
    case 'response':
    case 'resolution':
      appendSystemItem(items, 'llm', summary, {
        id: event.event_id,
        collapsible: Boolean(fullContent),
        responseBody: fullContent,
        title: formatMeetingSpeakerTitle(event),
        meetingSubstep: event.substep,
        meetingFinal: event.final !== false,
        deliberationGroupId: event.deliberation_group_id,
        guardrailFlags: Array.isArray(event.guardrail_flags) ? event.guardrail_flags : [],
      })
      break
    case 'extraction_done':
    case 'validation_result':
      appendSystemItem(items, 'system', summary || fullContent || 'Validation update', {
        id: event.event_id,
        collapsible: Boolean(fullContent && fullContent !== summary),
        responseBody: fullContent && fullContent !== summary ? fullContent : undefined,
      })
      break
    case 'phase_end':
    case 'phase_close':
      appendSystemItem(items, 'meeting_phase', formatMeetingPhaseBody(event), {
        id: event.event_id,
        title: formatPhaseName(event.phase),
      })
      break
    case 'build_step':
    case 'assemble_step': {
      const toolCallDetails = formatMeetingEventToolCalls(event)
      const missingFieldDetails = formatMissingContractFields(event)
      const stepDetails = toolCallDetails || missingFieldDetails || fullContent || undefined
      appendSystemItem(items, 'meeting_step', summary || fullContent || 'Execution step', {
        id: event.event_id,
        collapsible: Boolean(stepDetails),
        responseBody: stepDetails,
      })
      break
    }
  }
  return items
}
