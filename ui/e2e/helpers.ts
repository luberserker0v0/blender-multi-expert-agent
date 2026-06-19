import type { Page, WebSocketRoute } from '@playwright/test'
import type {
  ActivityEventEnvelope,
  ActivityItem,
  McpConnectionStatus,
  McpToolCallRecord,
  MultiStageProgressSnapshot,
  RetryPromptState,
  RunStatus,
  SavedSettings,
  SessionStateSnapshot,
  SessionSummary,
  WorkspaceDraft,
} from '../src/types'

export const TEST_SESSION_ID = 'e2e-test-session'

const DEFAULT_SETTINGS: SavedSettings = {
  agentOrchestratorUrl: 'http://127.0.0.1:4111',
  agentOrchestratorModel: '',
  keepAgentOrchestratorConversation: false,
  agentOrchestratorTimeoutSeconds: 120,
  maxPartRefinementRounds: 3,
  maxAssemblyRounds: 3,
  useYoloValidation: false,
  yoloModelPath: '',
  yoloViewpoints: 'front',
}

const DEFAULT_MCP_STATUS: McpConnectionStatus = {
  enabled: true,
  state: 'connected',
  message: 'Mock Blender MCP is connected.',
  tools: [
    { name: 'create_cube', description: 'Create a cube.' },
    { name: 'move_object', description: 'Move an object.' },
  ],
  server_name: 'blender',
}

function createEmptyProgress(): MultiStageProgressSnapshot {
  return {
    workflow_type: 'multi_stage_modeling',
    status: 'idle',
    task: '',
    stage: 'idle',
    stage_status: 'waiting_for_prompt',
    planning_llm_prompt_preview: '',
    llm_prompt_events: [],
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

function createDefaultRetryPrompt(sessionId: string): RetryPromptState {
  return {
    show: false,
    session_id: sessionId,
    remaining_retries: 0,
    decision_state: '',
    failure_reason: '',
    interaction_id: '',
    attempt_index: 0,
    next_attempt_index: 1,
    auto_retrying: false,
  }
}

function createDefaultRunStatus(sessionId: string): RunStatus {
  return {
    session_id: sessionId,
    workflow_status: 'idle',
    process_status: 'not_started',
    error_message: '',
    last_command: [],
    pid: null,
    exit_code: null,
    attempt_index: 0,
  }
}

function createDefaultWorkspace(): WorkspaceDraft {
  return {
    taskInput: '',
    referenceText: '',
    referenceImages: [],
  }
}

interface SessionStore {
  workspace: WorkspaceDraft
  activity: ActivityItem[]
  progress: MultiStageProgressSnapshot | null
  runStatus: RunStatus
  retryPrompt: RetryPromptState
  consoleLog: string
  mcpToolCalls: McpToolCallRecord[]
  serverCursor: string
}

interface MockBridgeState {
  settings: SavedSettings
  sessions: SessionSummary[]
  currentSessionId: string
  mcpStatus: McpConnectionStatus
  sessionStore: Record<string, SessionStore>
  nextSessionIndex: number
}

function createSessionStore(sessionId: string): SessionStore {
  return {
    workspace: createDefaultWorkspace(),
    activity: [],
    progress: null,
    runStatus: createDefaultRunStatus(sessionId),
    retryPrompt: createDefaultRetryPrompt(sessionId),
    consoleLog: '',
    mcpToolCalls: [],
    serverCursor: `${sessionId}:0`,
  }
}

function createInitialState(): MockBridgeState {
  return {
    settings: { ...DEFAULT_SETTINGS },
    sessions: [
      {
        id: TEST_SESSION_ID,
        title: 'E2E Test Session',
        updatedAt: '2024-01-01T00:00:00Z',
      },
    ],
    currentSessionId: TEST_SESSION_ID,
    mcpStatus: { ...DEFAULT_MCP_STATUS, tools: [...DEFAULT_MCP_STATUS.tools] },
    sessionStore: {
      [TEST_SESSION_ID]: createSessionStore(TEST_SESSION_ID),
    },
    nextSessionIndex: 1,
  }
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function mapSettingsToApi(settings: SavedSettings) {
  return {
    agent_orchestrator_base_url: settings.agentOrchestratorUrl,
    agent_orchestrator_model: settings.agentOrchestratorModel,
    agent_orchestrator_destroy_on_finish: !settings.keepAgentOrchestratorConversation,
    agent_orchestrator_timeout_seconds: settings.agentOrchestratorTimeoutSeconds,
    max_part_refinement_rounds: settings.maxPartRefinementRounds,
    max_assembly_rounds: settings.maxAssemblyRounds,
    use_yolo_perception: settings.useYoloValidation,
    yolo_model_path: settings.yoloModelPath,
    yolo_viewpoints: settings.yoloViewpoints
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
  }
}

function sessionTitleFromWorkspace(workspace: WorkspaceDraft) {
  return workspace.taskInput.trim() || workspace.referenceText.trim() || 'New modeling session'
}

function ensureSessionStore(state: MockBridgeState, sessionId: string) {
  if (!state.sessionStore[sessionId]) {
    state.sessionStore[sessionId] = createSessionStore(sessionId)
  }
  return state.sessionStore[sessionId]
}

function buildSessionSnapshot(state: MockBridgeState, sessionId: string): SessionStateSnapshot {
  const store = ensureSessionStore(state, sessionId)
  return {
    session_id: sessionId,
    workspace: cloneJson(store.workspace),
    activity: cloneJson(store.activity),
    progress: cloneJson(store.progress),
    run_status: cloneJson(store.runStatus),
    retry_prompt: cloneJson(store.retryPrompt),
    console_log: store.consoleLog,
    mcp_tool_calls: cloneJson(store.mcpToolCalls),
    mcp_status: cloneJson(state.mcpStatus),
    server_cursor: store.serverCursor,
    snapshot_generated_at: Date.now(),
  }
}

function createJsonResponse(body: unknown, status = 200) {
  return {
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  }
}

export interface MockBridgeController {
  getState(): MockBridgeState
  setSettings(settings: Partial<SavedSettings>): void
  setMcpStatus(status: Partial<McpConnectionStatus>): void
  setRunStatus(sessionId: string, patch: Partial<RunStatus>): void
  setConsoleLog(sessionId: string, consoleLog: string): void
  setMcpToolCalls(sessionId: string, toolCalls: McpToolCallRecord[]): void
  setProgress(sessionId: string, progress: MultiStageProgressSnapshot | null): void
  setRetryPrompt(sessionId: string, patch: Partial<RetryPromptState>): void
  setWorkspace(sessionId: string, patch: Partial<WorkspaceDraft>): void
  appendPersistedActivity(sessionId: string, items: ActivityItem[]): void
  setActivity(sessionId: string, items: ActivityItem[]): void
  setSessions(sessions: SessionSummary[], currentSessionId?: string): void
}

export async function mockBridgeApi(page: Page): Promise<MockBridgeController> {
  const state = createInitialState()
  await page.addInitScript(() => {
    localStorage.clear()
  })

  const controller: MockBridgeController = {
    getState: () => cloneJson(state),
    setSettings(patch) {
      state.settings = { ...state.settings, ...patch }
    },
    setMcpStatus(patch) {
      state.mcpStatus = { ...state.mcpStatus, ...patch }
    },
    setRunStatus(sessionId, patch) {
      const store = ensureSessionStore(state, sessionId)
      store.runStatus = { ...store.runStatus, ...patch, session_id: sessionId }
    },
    setConsoleLog(sessionId, consoleLog) {
      ensureSessionStore(state, sessionId).consoleLog = consoleLog
    },
    setMcpToolCalls(sessionId, toolCalls) {
      ensureSessionStore(state, sessionId).mcpToolCalls = cloneJson(toolCalls)
    },
    setProgress(sessionId, progress) {
      ensureSessionStore(state, sessionId).progress = cloneJson(progress)
    },
    setRetryPrompt(sessionId, patch) {
      const store = ensureSessionStore(state, sessionId)
      store.retryPrompt = { ...store.retryPrompt, ...patch, session_id: sessionId }
    },
    setWorkspace(sessionId, patch) {
      const store = ensureSessionStore(state, sessionId)
      store.workspace = { ...store.workspace, ...patch }
      const nextTitle = sessionTitleFromWorkspace(store.workspace)
      state.sessions = state.sessions.map((session) =>
        session.id === sessionId ? { ...session, title: nextTitle, updatedAt: 'just now' } : session,
      )
    },
    appendPersistedActivity(sessionId, items) {
      ensureSessionStore(state, sessionId).activity.push(...cloneJson(items))
    },
    setActivity(sessionId, items) {
      ensureSessionStore(state, sessionId).activity = cloneJson(items)
    },
    setSessions(sessions, currentSessionId) {
      state.sessions = cloneJson(sessions)
      if (currentSessionId !== undefined) {
        state.currentSessionId = currentSessionId
      }
      for (const session of sessions) {
        ensureSessionStore(state, session.id)
      }
    },
  }

  await page.route('**/api/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const path = url.pathname
    const method = request.method()
    const body = request.postDataJSON?.() as Record<string, unknown> | undefined

    if (path === '/api/bootstrap' && method === 'GET') {
      return route.fulfill(
        createJsonResponse({
          sessions: cloneJson(state.sessions),
          current_session_id: state.currentSessionId,
          settings: mapSettingsToApi(state.settings),
          mcp_status: cloneJson(state.mcpStatus),
        }),
      )
    }

    if (path === '/api/session/state' && method === 'GET') {
      const sessionId = url.searchParams.get('session_id') || state.currentSessionId
      return route.fulfill(createJsonResponse(buildSessionSnapshot(state, sessionId)))
    }

    if (path === '/api/activity/snapshot' && method === 'GET') {
      const sessionId = url.searchParams.get('session_id') || state.currentSessionId
      return route.fulfill(createJsonResponse(buildSessionSnapshot(state, sessionId)))
    }

    if (path === '/api/mcp/status' && method === 'GET') {
      return route.fulfill(createJsonResponse(cloneJson(state.mcpStatus)))
    }

    if (path === '/api/mcp/connect' && method === 'POST') {
      return route.fulfill(createJsonResponse(cloneJson(state.mcpStatus)))
    }

    if (path === '/api/mcp/tool-calls' && method === 'GET') {
      const sessionId = url.searchParams.get('session_id') || state.currentSessionId
      const store = ensureSessionStore(state, sessionId)
      return route.fulfill(createJsonResponse({ tool_calls: cloneJson(store.mcpToolCalls) }))
    }

    if (path === '/api/run/status' && method === 'GET') {
      const sessionId = url.searchParams.get('session_id') || state.currentSessionId
      const store = ensureSessionStore(state, sessionId)
      return route.fulfill(createJsonResponse(cloneJson(store.runStatus)))
    }

    if (path === '/api/run/console' && method === 'GET') {
      const sessionId = url.searchParams.get('session_id') || state.currentSessionId
      const store = ensureSessionStore(state, sessionId)
      return route.fulfill(createJsonResponse({ content: store.consoleLog }))
    }

    if (path === '/api/session/workspace' && method === 'POST') {
      const sessionId = String(body?.session_id ?? state.currentSessionId)
      controller.setWorkspace(sessionId, {
        taskInput: String(body?.task_input ?? ''),
        referenceText: String(body?.reference_text ?? ''),
        referenceImages: Array.isArray(body?.reference_images) ? body?.reference_images.map(String) : [],
      })
      return route.fulfill(createJsonResponse({ ok: true }))
    }

    if (path === '/api/activity/append' && method === 'POST') {
      const sessionId = String(body?.session_id ?? state.currentSessionId)
      const items = Array.isArray(body?.activity) ? (body?.activity as ActivityItem[]) : []
      controller.appendPersistedActivity(sessionId, items)
      return route.fulfill(createJsonResponse({ ok: true }))
    }

    if (path === '/api/session/new' && method === 'POST') {
      const sessionId = `e2e-test-session-${state.nextSessionIndex}`
      state.nextSessionIndex += 1
      ensureSessionStore(state, sessionId)
      state.sessions = [
        {
          id: sessionId,
          title: 'New modeling session',
          updatedAt: 'just now',
        },
        ...state.sessions,
      ]
      return route.fulfill(createJsonResponse({ session_id: sessionId }))
    }

    if (path === '/api/session/current' && method === 'POST') {
      state.currentSessionId = String(body?.session_id ?? '')
      return route.fulfill(createJsonResponse({ ok: true }))
    }

    if (path === '/api/session/delete' && method === 'POST') {
      const sessionId = String(body?.session_id ?? '')
      state.sessions = state.sessions.filter((session) => session.id !== sessionId)
      delete state.sessionStore[sessionId]
      if (state.currentSessionId === sessionId) {
        state.currentSessionId = state.sessions[0]?.id ?? ''
      }
      return route.fulfill(createJsonResponse({ deleted: true }))
    }

    if (path === '/api/agent-orchestrator/live' && method === 'POST') {
      return route.fulfill(
        createJsonResponse({
          ok: true,
          name: 'agent_orchestrator_health',
          message: 'Agent Orchestrator is reachable.',
        }),
      )
    }

    if (path === '/api/agent-orchestrator/models' && method === 'POST') {
      return route.fulfill(
        createJsonResponse({
          ok: true,
          models: [
            { id: 'openai/gpt-5', provider: 'openai', model: 'gpt-5' },
            { id: 'anthropic/claude-3-5-sonnet', provider: 'anthropic', model: 'claude-3-5-sonnet' },
          ],
          message: 'Loaded 2 Agent Orchestrator models.',
        }),
      )
    }

    if (path === '/api/diagnostics/live' && method === 'POST') {
      return route.fulfill(
        createJsonResponse({
          ok: state.mcpStatus.state === 'connected',
          checks: [
            { name: 'agent_orchestrator_health', ok: true, message: 'Agent Orchestrator is reachable.' },
            { name: 'agent_orchestrator_conversation_ready', ok: true, message: 'Agent Orchestrator conversation can be prepared.' },
            { name: 'blender_mcp_connect', ok: state.mcpStatus.state === 'connected', message: state.mcpStatus.message },
          ],
        }),
      )
    }

    if (path === '/api/settings' && method === 'POST') {
      state.settings = {
        agentOrchestratorUrl: String(body?.agent_orchestrator_base_url ?? state.settings.agentOrchestratorUrl),
        agentOrchestratorModel: String(body?.agent_orchestrator_model ?? state.settings.agentOrchestratorModel),
        keepAgentOrchestratorConversation: !Boolean(body?.agent_orchestrator_destroy_on_finish ?? !state.settings.keepAgentOrchestratorConversation),
        agentOrchestratorTimeoutSeconds: Number(body?.agent_orchestrator_timeout_seconds ?? state.settings.agentOrchestratorTimeoutSeconds),
        maxPartRefinementRounds: Number(body?.max_part_refinement_rounds ?? state.settings.maxPartRefinementRounds),
        maxAssemblyRounds: Number(body?.max_assembly_rounds ?? state.settings.maxAssemblyRounds),
        useYoloValidation: Boolean(body?.use_yolo_perception ?? state.settings.useYoloValidation),
        yoloModelPath: String(body?.yolo_model_path ?? state.settings.yoloModelPath),
        yoloViewpoints: Array.isArray(body?.yolo_viewpoints)
          ? body!.yolo_viewpoints.map(String).join(', ')
          : state.settings.yoloViewpoints,
      }
      return route.fulfill(createJsonResponse({ ok: true }))
    }

    if (path === '/api/run/start' && method === 'POST') {
      const sessionId = String(body?.session_id ?? state.currentSessionId)
      const store = ensureSessionStore(state, sessionId)
      store.runStatus = {
        ...store.runStatus,
        session_id: sessionId,
        workflow_status: 'running',
        process_status: 'running',
        error_message: '',
      }
      return route.fulfill(
        createJsonResponse({
          started: true,
          session_id: sessionId,
          run_status: cloneJson(store.runStatus),
        }),
      )
    }

    if (path === '/api/run/stop' && method === 'POST') {
      const sessionId = String(body?.session_id ?? state.currentSessionId)
      const store = ensureSessionStore(state, sessionId)
      store.runStatus = {
        ...store.runStatus,
        workflow_status: 'stopping',
        process_status: 'stopping',
      }
      return route.fulfill(
        createJsonResponse({
          stopped: true,
          run_status: cloneJson(store.runStatus),
        }),
      )
    }

    if (path === '/api/run/retry' && method === 'POST') {
      const sessionId = String(body?.session_id ?? state.currentSessionId)
      const store = ensureSessionStore(state, sessionId)
      store.runStatus = {
        ...store.runStatus,
        workflow_status: 'running',
        process_status: 'running',
      }
      return route.fulfill(
        createJsonResponse({
          started: true,
          session_id: sessionId,
          run_status: cloneJson(store.runStatus),
        }),
      )
    }

    if (path === '/api/run/retry/stop' && method === 'POST') {
      return route.fulfill(createJsonResponse({ ok: true }))
    }

    return route.continue()
  })

  return controller
}

export interface MockActivitySocketController {
  setup(): Promise<void>
  getRoute(): WebSocketRoute | null
  sendMeetingEvent(event: Record<string, unknown>, sessionId?: string): void
  sendActivityAppended(items: ActivityItem[], sessionId?: string): void
  sendSnapshotRequired(sessionId?: string): void
  sendSessionSnapshot(snapshot: Partial<SessionStateSnapshot>, sessionId?: string): void
  sendSnapshot(snapshot: { progress?: MultiStageProgressSnapshot | null; run_status?: Partial<RunStatus>; retry_prompt?: Partial<RetryPromptState> }, sessionId?: string): void
}

export function createMockActivityWebSocket(
  page: Page,
  controller?: MockBridgeController,
): MockActivitySocketController {
  let route: WebSocketRoute | null = null
  let sequence = 0

  const setupPromise = page.routeWebSocket(/ws:\/\/.*\/ws\/activity/, (ws) => {
    route = ws
  })

  function envelope(
    type: ActivityEventEnvelope['type'],
    sessionId: string,
    data?: Record<string, unknown>,
  ): ActivityEventEnvelope {
    sequence += 1
    return {
      type,
      session_id: sessionId,
      event_id: `${sessionId}:${type}:${sequence}`,
      sequence,
      server_cursor: `${sessionId}:${sequence}`,
      data,
    }
  }

  function send(payload: ActivityEventEnvelope) {
    if (route) {
      route.send(JSON.stringify(payload))
    }
  }

  return {
    setup: () => setupPromise,
    getRoute: () => route,
    sendMeetingEvent(event, sessionId = TEST_SESSION_ID) {
      send(envelope('meeting_event', sessionId, event))
    },
    sendActivityAppended(items, sessionId = TEST_SESSION_ID) {
      controller?.appendPersistedActivity(sessionId, items)
      send(envelope('activity_appended', sessionId, { items }))
    },
    sendSnapshotRequired(sessionId = TEST_SESSION_ID) {
      send(envelope('snapshot_required', sessionId))
    },
    sendSessionSnapshot(snapshot, sessionId = TEST_SESSION_ID) {
      if (controller) {
        if (snapshot.workspace) controller.setWorkspace(sessionId, snapshot.workspace)
        if (snapshot.activity) controller.setActivity(sessionId, snapshot.activity)
        if (snapshot.progress !== undefined) controller.setProgress(sessionId, snapshot.progress)
        if (snapshot.run_status) controller.setRunStatus(sessionId, snapshot.run_status)
        if (snapshot.retry_prompt) controller.setRetryPrompt(sessionId, snapshot.retry_prompt)
        if (typeof snapshot.console_log === 'string') controller.setConsoleLog(sessionId, snapshot.console_log)
        if (snapshot.mcp_tool_calls) controller.setMcpToolCalls(sessionId, snapshot.mcp_tool_calls)
        if (snapshot.mcp_status) controller.setMcpStatus(snapshot.mcp_status)
      }
      send(envelope('snapshot_required', sessionId))
    },
    sendSnapshot(snapshot, sessionId = TEST_SESSION_ID) {
      this.sendSessionSnapshot(
        {
          progress: snapshot.progress ?? null,
          run_status: snapshot.run_status
            ? {
                ...createDefaultRunStatus(sessionId),
                ...snapshot.run_status,
                session_id: sessionId,
              }
            : undefined,
          retry_prompt: snapshot.retry_prompt
            ? {
                ...createDefaultRetryPrompt(sessionId),
                ...snapshot.retry_prompt,
                session_id: sessionId,
              }
            : undefined,
        },
        sessionId,
      )
    },
  }
}
