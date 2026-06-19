import { expect, type Page } from '@playwright/test'
import {
  activityItemsFromMeetingEvent,
  createInitialActivityMarkers,
  deriveActivityUpdatesFromProgress,
} from '../src/domain/activity'
import type {
  ActivityItem,
  ActivityEventEnvelope,
  McpConnectionStatus,
  McpToolCallRecord,
  MeetingEvent,
  RetryPromptState,
  RunStatus,
  SessionStateSnapshot,
} from '../src/types'

export interface ActivityTimelineEntry {
  index: number
  id: string
  kind: string
  title: string
  body: string
}

export interface EventTraceEntry extends ActivityEventEnvelope {
  data: Record<string, unknown>
}

export interface ActivityEventTracePayload {
  session_id: string
  events: EventTraceEntry[]
  server_cursor: string
  snapshot_generated_at: number
}

export interface ExpectedActivityFromEvent extends ActivityTimelineEntry {
  sourceEventId: string
  sourceSequence: number
}

export interface RuntimeToolCallEntry {
  index: number
  toolName: string
  status: 'ok' | 'error'
  timestamp: string
  argumentsText: string
}

export interface RuntimeTruthPayload {
  session_id: string
  run_status: RunStatus
  console_log: string
  mcp_tool_calls: McpToolCallRecord[]
  mcp_status: McpConnectionStatus
  snapshot_generated_at: number
}

export interface RenderedRuntimePanel {
  workflowStatus: string
  processStatus: string
  pid: string
  exitCode: string
  mcpState: string
  consoleText: string
  consoleLines: string[]
  toolCalls: RuntimeToolCallEntry[]
}

export interface InspectorBlockItemEntry {
  label: string
  value: string
}

export interface InspectorBlockEntry {
  title: string
  items: InspectorBlockItemEntry[]
}

export interface InspectorTruthPayload {
  session_id: string
  progress: SessionStateSnapshot['progress']
  selection_kind: 'task' | 'part-round' | 'assembly-round' | 'none'
  summary: {
    status: string
    stage: string
    active_task: string
    detected_parts: string
    completed_tasks: string
    stop_reason: string
  }
  latest_capture: string
  final_validation_capture: string
  selected_task_title: string
  inspector_blocks: InspectorBlockEntry[]
  snapshot_generated_at: number
}

export interface RenderedInspectorPanel {
  selectionKind: 'task' | 'part-round' | 'assembly-round' | 'none'
  status: string
  stage: string
  activeTask: string
  detectedParts: string
  completedTasks: string
  stopReason: string
  latestCapture: string
  finalValidationCapture: string
  selectedTaskTitle: string
  blocks: InspectorBlockEntry[]
}

export interface RetryTruthPayload {
  session_id: string
  run_status: RunStatus
  retry_prompt: RetryPromptState
  pending_interaction: Record<string, unknown>
  progress: SessionStateSnapshot['progress']
  activity: ActivityItem[]
  failure_triage?: Record<string, unknown>
  failure_category?: string
  planning_summary?: string
  blocking_constraint_refs?: string[]
  server_cursor: string
  snapshot_generated_at: number
}

export interface RenderedRetryCardState {
  visible: boolean
  autoVisible: boolean
  summary: string
  currentAttempt: string
  nextAttempt: string
  autoSummary: string
  remainingText: string
}

function activityRenderSignature(item: Pick<ActivityItem, 'kind' | 'title' | 'body' | 'timestamp' | 'pairKey' | 'llmDirection' | 'responseBody'>) {
  return [
    item.kind,
    item.title,
    item.body,
    item.timestamp,
    item.pairKey ?? '',
    item.llmDirection ?? '',
    item.responseBody ?? '',
  ].join('::')
}

function dedupeActivityForExpectation(items: ActivityItem[]) {
  const seenIds = new Set<string>()
  const seenSignatures = new Set<string>()
  return items.filter((item) => {
    if (item.id) {
      if (seenIds.has(item.id)) {
        return false
      }
      seenIds.add(item.id)
    }
    const signature = activityRenderSignature(item)
    if (seenSignatures.has(signature)) {
      return false
    }
    seenSignatures.add(signature)
    return true
  })
}

export async function createFreshSessionFromUi(page: Page) {
  const previousSessionId = await readCurrentSessionId(page)
  await page.locator('aside').getByRole('button', { name: 'New Session' }).click()
  await expect(page.getByText('Current Session')).toBeVisible()
  await expect
    .poll(async () => await readCurrentSessionId(page), { timeout: 20000 })
    .not.toBe(previousSessionId)
  return readCurrentSessionId(page)
}

export async function readCurrentSessionId(page: Page) {
  return page.evaluate(() => {
    const raw = window.localStorage.getItem('ai3d-react-ui-store')
    if (!raw) return ''
    const parsed = JSON.parse(raw) as { state?: { currentSessionId?: string } }
    return parsed.state?.currentSessionId ?? ''
  })
}

export async function selectSessionFromSidebar(page: Page, title: string) {
  await page.locator('aside').getByRole('button', { name: new RegExp(title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) }).click()
}

export async function readMessageCount(page: Page) {
  const text = await page.getByText(/\d+ messages/).textContent()
  return Number(text?.match(/\d+/)?.[0] ?? '0')
}

export async function waitForWorkflowState(page: Page, state: 'running' | 'completed' | 'failed', timeout = 20000) {
  await expect(page.getByText(`workflow: ${state}`)).toBeVisible({ timeout })
}

export async function waitForActivityTimelineLength(page: Page, minimum: number, timeout = 20000) {
  await expect
    .poll(async () => (await readRenderedActivityTimeline(page)).length, { timeout })
    .toBeGreaterThanOrEqual(minimum)
}

export async function openRuntimeLog(page: Page) {
  await page.getByRole('button', { name: 'Runtime Log' }).click()
  await expect(page.getByRole('heading', { name: 'Runtime Console' })).toBeVisible()
}

export async function openInspector(page: Page) {
  await page.getByRole('button', { name: 'Inspector' }).click()
  await expect(page.getByRole('heading', { name: 'Progress Inspector' })).toBeVisible()
}

export async function closeTopPanel(page: Page) {
  await page.evaluate(() => {
    const button = document.querySelector(
      'div.fixed.left-0.right-0.top-0.z-50.translate-y-0 button',
    ) as HTMLButtonElement | null
    button?.click()
  })
  await page.waitForTimeout(200)
}

export async function fetchBackendActivityTruth(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/test/activity-truth?session_id=${encodeURIComponent(sessionId)}`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as {
    session_id: string
    snapshot: SessionStateSnapshot
    activity: ActivityItem[]
    server_cursor: string
    snapshot_generated_at: number
  }
}

export async function fetchBackendActivityEventTrace(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/test/activity-event-trace?session_id=${encodeURIComponent(sessionId)}`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as ActivityEventTracePayload
}

export async function fetchBackendRuntimeTruth(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/test/runtime-truth?session_id=${encodeURIComponent(sessionId)}`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as RuntimeTruthPayload
}

export async function fetchBackendInspectorTruth(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/test/inspector-truth?session_id=${encodeURIComponent(sessionId)}`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as InspectorTruthPayload
}

export async function fetchBackendRetryTruth(page: Page, sessionId: string) {
  const response = await page.request.get(`/api/test/retry-truth?session_id=${encodeURIComponent(sessionId)}`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as RetryTruthPayload
}

export function buildExpectedActivityTimeline(snapshot: SessionStateSnapshot): ActivityTimelineEntry[] {
  const persisted = dedupeActivityForExpectation(snapshot.activity ?? []).map(normalizeActivityItem)
  if (!snapshot.progress) {
    return persisted.map((item, index) => ({ ...item, index }))
  }
  const derived = dedupeActivityForExpectation(deriveActivityUpdatesFromProgress(
    snapshot.progress,
    snapshot.run_status,
    snapshot.retry_prompt,
    createInitialActivityMarkers(),
  ).items).map(normalizeActivityItem)
  return [...persisted, ...derived].map((item, index) => ({ ...item, index }))
}

export async function readRenderedActivityTimeline(page: Page): Promise<ActivityTimelineEntry[]> {
  const items = page.getByTestId('activity-item')
  const count = await items.count()
  const timeline: ActivityTimelineEntry[] = []

  for (let index = 0; index < count; index += 1) {
    const item = items.nth(index)
    const kind =
      (await item.getAttribute('data-activity-kind')) ??
      (await item.getByTestId('activity-item-kind').textContent()) ??
      ''
    const id = (await item.getAttribute('data-activity-id')) ?? ''
    const title = ((await item.getByTestId('activity-item-title').textContent()) ?? '').trim()
    const body = ((await item.getByTestId('activity-item-body').first().textContent()) ?? '').trim()
    timeline.push({
      index,
      id: id.trim(),
      kind: kind.trim(),
      title,
      body,
    })
  }

  return timeline
}

export async function expectActivityTimelineToMatch(page: Page, expected: ActivityTimelineEntry[]) {
  await expect
    .poll(async () => (await readRenderedActivityTimeline(page)).length, { timeout: 20000 })
    .toBeGreaterThanOrEqual(expected.length)

  const rendered = await readRenderedActivityTimeline(page)
  let searchStart = 0
  for (const expectedEntry of expected) {
    const matchedIndex = rendered.findIndex((entry, index) => {
      if (index < searchStart) {
        return false
      }
      return (
        entry.kind === expectedEntry.kind &&
        entry.title === expectedEntry.title &&
        entry.body.includes(expectedEntry.body)
      )
    })
    expect(matchedIndex, `Missing expected activity entry "${expectedEntry.title}"`).toBeGreaterThanOrEqual(searchStart)
    searchStart = matchedIndex + 1
  }

  const latest = rendered.at(-1)
  expect(latest?.body).not.toBe('idle / waiting_for_prompt')
  expect(rendered.some((entry) => entry.body.startsWith('Prompt > '))).toBe(false)
  expect(rendered.some((entry) => entry.body.startsWith('Response > '))).toBe(false)
}

export function buildExpectedActivityFromEventTrace(trace: ActivityEventTracePayload): ExpectedActivityFromEvent[] {
  const expected: ExpectedActivityFromEvent[] = []
  const seenIds = new Set<string>()
  const seenSignatures = new Set<string>()
  const pushExpected = (
    item: ActivityItem,
    sourceEventId: string,
    sourceSequence: number,
  ) => {
    if (item.kind === 'meeting_phase') {
      return
    }
    if (item.id) {
      if (seenIds.has(item.id)) {
        return
      }
      seenIds.add(item.id)
    }
    const signature = activityRenderSignature(item)
    if (seenSignatures.has(signature)) {
      return
    }
    seenSignatures.add(signature)
    expected.push({
      index: expected.length,
      id: item.id,
      kind: item.kind,
      title: item.title.trim(),
      body: item.body.trim(),
      sourceEventId,
      sourceSequence,
    })
  }
  for (const event of trace.events) {
    if (event.type === 'meeting_event') {
      const mapped = activityItemsFromMeetingEvent(event.data as unknown as MeetingEvent)
      for (const item of mapped) {
        pushExpected(
          {
            ...item,
            id: item.id || String((event.data as Record<string, unknown>).event_id ?? event.event_id),
          },
          event.event_id,
          event.sequence,
        )
      }
      continue
    }
    if (event.type === 'activity_appended' && Array.isArray(event.data.items)) {
      for (const item of event.data.items as ActivityItem[]) {
        pushExpected(item, event.event_id, event.sequence)
      }
    }
  }
  return expected
}

export async function expectActivityEventTraceInRenderedOrder(page: Page, trace: ActivityEventTracePayload) {
  expect(trace.events.length).toBeGreaterThan(0)
  for (let index = 1; index < trace.events.length; index += 1) {
    expect(trace.events[index].sequence).toBeGreaterThan(trace.events[index - 1].sequence)
  }

  const expected = buildExpectedActivityFromEventTrace(trace)
  expect(expected.length).toBeGreaterThan(0)

  const rendered = await readRenderedActivityTimeline(page)
  let searchStart = 0
  for (const expectedEntry of expected) {
    const matchedIndex = rendered.findIndex((entry, index) => {
      if (index < searchStart) {
        return false
      }
      return (
        entry.kind === expectedEntry.kind &&
        entry.title === expectedEntry.title &&
        entry.body.includes(expectedEntry.body)
      )
    })
    expect(matchedIndex, `Missing event-driven activity for sequence ${expectedEntry.sourceSequence}`).toBeGreaterThanOrEqual(
      searchStart,
    )
    searchStart = matchedIndex + 1
  }
}

export async function expectNoDuplicateRenderedEventDrivenItems(page: Page, trace: ActivityEventTracePayload) {
  const expected = buildExpectedActivityFromEventTrace(trace)
  const rendered = await readRenderedActivityTimeline(page)
  const signatures = new Map<string, number>()

  for (const expectedEntry of expected) {
    const signature = `${expectedEntry.kind}::${expectedEntry.title}::${expectedEntry.body}`
    const matches = rendered.filter(
      (entry) =>
        entry.kind === expectedEntry.kind &&
        entry.title === expectedEntry.title &&
        entry.body.includes(expectedEntry.body),
    )
    signatures.set(signature, matches.length)
  }

  for (const [signature, count] of signatures.entries()) {
    expect(count, `Expected a single rendered activity item for ${signature}`).toBe(1)
  }

  expect(rendered.at(-1)?.body).not.toBe('idle / waiting_for_prompt')
}

export async function readRenderedRuntimePanel(page: Page): Promise<RenderedRuntimePanel> {
  const workflowStatus = ((await page.getByTestId('runtime-metric-workflow-value').textContent()) ?? '').trim()
  const processStatus = ((await page.getByTestId('runtime-metric-process-value').textContent()) ?? '').trim()
  const pid = ((await page.getByTestId('runtime-metric-pid-value').textContent()) ?? '').trim()
  const exitCode = ((await page.getByTestId('runtime-metric-exit-code-value').textContent()) ?? '').trim()
  const mcpState = ((await page.getByTestId('runtime-metric-mcp-state-value').textContent()) ?? '').trim()
  const consoleText = ((await page.getByTestId('runtime-console').textContent()) ?? '').trim()
  const toolCallItems = page.getByTestId('runtime-tool-call-item')
  const toolCallCount = await toolCallItems.count()
  const toolCalls: RuntimeToolCallEntry[] = []

  for (let index = 0; index < toolCallCount; index += 1) {
    const item = toolCallItems.nth(index)
    toolCalls.push({
      index,
      toolName: ((await item.getByTestId('runtime-tool-call-name').textContent()) ?? '').trim(),
      status: (((await item.getByTestId('runtime-tool-call-status').textContent()) ?? '').trim() as 'ok' | 'error'),
      timestamp: ((await item.getByTestId('runtime-tool-call-timestamp').textContent()) ?? '').trim(),
      argumentsText: ((await item.getByTestId('runtime-tool-call-arguments').textContent()) ?? '').trim(),
    })
  }

  return {
    workflowStatus,
    processStatus,
    pid,
    exitCode,
    mcpState,
    consoleText,
    consoleLines: splitRuntimeLines(consoleText),
    toolCalls,
  }
}

export async function expectRuntimePanelToMatch(page: Page, truth: RuntimeTruthPayload) {
  const expectedConsoleLines = splitRuntimeLines(truth.console_log)
  await expect
    .poll(
      async () => {
        const rendered = await readRenderedRuntimePanel(page)
        const hasAllConsoleLines = expectedConsoleLines.every((line) => rendered.consoleText.includes(line))
        const hasToolCalls = rendered.toolCalls.length === truth.mcp_tool_calls.length
        return (
          rendered.workflowStatus === truth.run_status.workflow_status &&
          rendered.processStatus === truth.run_status.process_status &&
          rendered.pid === (truth.run_status.pid ? String(truth.run_status.pid) : 'N/A') &&
          rendered.exitCode ===
            (truth.run_status.exit_code !== null ? String(truth.run_status.exit_code) : 'N/A') &&
          rendered.mcpState === truth.mcp_status.state &&
          hasAllConsoleLines &&
          hasToolCalls
        )
      },
      { timeout: 20000 },
    )
    .toBe(true)

  const rendered = await readRenderedRuntimePanel(page)
  expect(rendered.workflowStatus).toBe(truth.run_status.workflow_status)
  expect(rendered.processStatus).toBe(truth.run_status.process_status)
  expect(rendered.pid).toBe(truth.run_status.pid ? String(truth.run_status.pid) : 'N/A')
  expect(rendered.exitCode).toBe(truth.run_status.exit_code !== null ? String(truth.run_status.exit_code) : 'N/A')
  expect(rendered.mcpState).toBe(truth.mcp_status.state)

  expect(rendered.consoleLines.length).toBeGreaterThanOrEqual(expectedConsoleLines.length)
  for (const line of expectedConsoleLines) {
    expect(rendered.consoleText).toContain(line)
  }

  expect(rendered.toolCalls).toHaveLength(truth.mcp_tool_calls.length)
  truth.mcp_tool_calls.forEach((entry, index) => {
    const actual = rendered.toolCalls[index]
    expect(actual.toolName).toBe(entry.tool_name)
    expect(actual.status).toBe(entry.is_error ? 'error' : 'ok')
    expect(actual.timestamp).toBe(entry.timestamp)
    expect(actual.argumentsText).toContain(JSON.stringify(entry.arguments, null, 2).trim())
  })
}

export async function readRenderedInspectorPanel(page: Page): Promise<RenderedInspectorPanel> {
  const selectionKind =
    (((await page.getByTestId('inspector-panel').getAttribute('data-selection-kind')) ?? 'none').trim() as
      | 'task'
      | 'part-round'
      | 'assembly-round'
      | 'none')
  const status = ((await page.getByTestId('inspector-metric-status-value').textContent()) ?? '').trim()
  const stage = ((await page.getByTestId('inspector-metric-stage-value').textContent()) ?? '').trim()
  const activeTask = ((await page.getByTestId('inspector-metric-active-task-value').textContent()) ?? '').trim()
  const detectedParts = ((await page.getByTestId('inspector-metric-detected-parts-value').textContent()) ?? '').trim()
  const completedTasks = ((await page.getByTestId('inspector-metric-completed-tasks-value').textContent()) ?? '').trim()
  const stopReason = ((await page.getByTestId('inspector-metric-stop-reason-value').textContent()) ?? '').trim()
  const latestCapture = ((await page.getByTestId('inspector-capture-latest-path').textContent()) ?? '').trim()
  const finalValidationCapture = ((await page.getByTestId('inspector-capture-final-validation-path').textContent()) ?? '').trim()
  const selectedTaskTitle = ((await page.getByTestId('inspector-selected-task-title').textContent()) ?? '').trim()
  const blockLocators = page.getByTestId('inspector-block')
  const blockCount = await blockLocators.count()
  const blocks: InspectorBlockEntry[] = []

  for (let index = 0; index < blockCount; index += 1) {
    const block = blockLocators.nth(index)
    const title = ((await block.getByTestId('inspector-block-title').textContent()) ?? '').trim()
    const itemLocators = block.getByTestId('inspector-block-item')
    const itemCount = await itemLocators.count()
    const items: InspectorBlockItemEntry[] = []
    for (let itemIndex = 0; itemIndex < itemCount; itemIndex += 1) {
      const item = itemLocators.nth(itemIndex)
      items.push({
        label: ((await item.getByTestId('inspector-block-item-label').textContent()) ?? '').trim(),
        value: ((await item.getByTestId('inspector-block-item-value').textContent()) ?? '').trim(),
      })
    }
    blocks.push({ title, items })
  }

  return {
    selectionKind,
    status,
    stage,
    activeTask,
    detectedParts,
    completedTasks,
    stopReason,
    latestCapture,
    finalValidationCapture,
    selectedTaskTitle,
    blocks,
  }
}

export async function expectInspectorPanelToMatch(page: Page, truth: InspectorTruthPayload) {
  if (truth.progress.status === 'idle') {
    await expect(page.getByRole('heading', { name: 'Progress Inspector' })).toBeVisible({ timeout: 20000 })
    await expect(page.getByTestId('inspector-panel')).toHaveCount(0)
    return
  }

  await expect.poll(async () => (await readRenderedInspectorPanel(page)).status, { timeout: 20000 }).toBe(
    truth.summary.status,
  )

  const rendered = await readRenderedInspectorPanel(page)
  expect(rendered.selectionKind).toBe(truth.selection_kind)
  expect(rendered.status).toBe(truth.summary.status)
  expect(rendered.stage).toBe(truth.summary.stage)
  expect(rendered.activeTask).toBe(truth.summary.active_task)
  expect(rendered.detectedParts).toBe(truth.summary.detected_parts)
  expect(rendered.completedTasks).toBe(truth.summary.completed_tasks)
  expect(rendered.stopReason).toBe(truth.summary.stop_reason)
  expect(rendered.latestCapture).toBe(truth.latest_capture)
  expect(rendered.finalValidationCapture).toBe(truth.final_validation_capture)
  expect(rendered.selectedTaskTitle).toBe(truth.selected_task_title)
  expect(rendered.blocks).toHaveLength(truth.inspector_blocks.length)

  truth.inspector_blocks.forEach((expectedBlock, index) => {
    const actualBlock = rendered.blocks[index]
    expect(actualBlock.title).toBe(expectedBlock.title)
    expect(actualBlock.items).toHaveLength(expectedBlock.items.length)
    expectedBlock.items.forEach((expectedItem, itemIndex) => {
      const actualItem = actualBlock.items[itemIndex]
      expect(actualItem.label).toBe(expectedItem.label)
      expect(actualItem.value).toBe(expectedItem.value)
    })
  })
}

export async function readRenderedRetryCard(page: Page): Promise<RenderedRetryCardState> {
  const retryCard = page.getByTestId('retry-card')
  const autoCard = page.getByTestId('retry-auto-card')
  const remainingLocator = page.getByTestId('retry-auto-remaining')
  const visible = await retryCard.isVisible().catch(() => false)
  const autoVisible = await autoCard.isVisible().catch(() => false)
  const remainingVisible = autoVisible ? await remainingLocator.isVisible().catch(() => false) : false

  return {
    visible,
    autoVisible,
    summary: visible ? (((await page.getByTestId('retry-card-summary').textContent()) ?? '').trim()) : '',
    currentAttempt: visible ? (((await page.getByTestId('retry-card-current-attempt').textContent()) ?? '').trim()) : '',
    nextAttempt: visible ? (((await page.getByTestId('retry-card-next-attempt').textContent()) ?? '').trim()) : '',
    autoSummary: autoVisible ? (((await page.getByTestId('retry-auto-summary').textContent()) ?? '').trim()) : '',
    remainingText: remainingVisible ? (((await remainingLocator.textContent()) ?? '').trim()) : '',
  }
}

export async function expectRetryCardToMatch(page: Page, truth: RetryTruthPayload) {
  await expect
    .poll(async () => (await readRenderedRetryCard(page)).visible, { timeout: 20000 })
    .toBe(Boolean(truth.retry_prompt.show))

  const rendered = await readRenderedRetryCard(page)
  expect(rendered.visible).toBe(Boolean(truth.retry_prompt.show))
  expect(rendered.autoVisible).toBe(Boolean(truth.retry_prompt.auto_retrying))

  if (truth.retry_prompt.show) {
    expect(rendered.summary).toContain('The run is paused and waiting for your retry decision.')
    if ((truth.retry_prompt.failure_reason ?? '').trim()) {
      expect(rendered.summary).toContain(String(truth.retry_prompt.failure_reason).trim())
    }
    expect(rendered.currentAttempt).toContain(String(truth.retry_prompt.attempt_index ?? truth.run_status.attempt_index ?? 0))
    expect(rendered.nextAttempt).toContain(String(truth.retry_prompt.next_attempt_index ?? (truth.run_status.attempt_index ?? 0) + 1))
  }

  if (truth.retry_prompt.auto_retrying) {
    expect(rendered.autoSummary).toContain(
      String(truth.retry_prompt.next_attempt_index ?? truth.run_status.attempt_index ?? 1),
    )
    if ((truth.retry_prompt.remaining_retries ?? 0) > 0) {
      expect(rendered.remainingText).toContain(String(truth.retry_prompt.remaining_retries))
    }
  }
}

function normalizeActivityItem(item: ActivityItem) {
  return {
    id: item.id,
    kind: item.kind,
    title: item.title.trim(),
    body: item.body.trim(),
  }
}

function splitRuntimeLines(value: string) {
  return value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
}
